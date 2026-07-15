from fastapi import APIRouter, Request, Depends, BackgroundTasks
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.middleware.slack_verification import verify_slack_signature
from app.slack.validator import SlackMessageValidator
from app.core.config import settings
from loguru import logger
import json

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/events", dependencies=[Depends(verify_slack_signature)])
@limiter.limit("30/minute")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    
    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
        
    event = data.get("event", {})
    event_type = event.get("type")
    
    # We only care about messages in the configured channel
    if event_type == "message":
        channel = event.get("channel")
        user = event.get("user")
        text = event.get("text", "")
        subtype = event.get("subtype")
        event_id = data.get("event_id")
        
        # Ignore bot messages, edits, deletions, and thread replies
        if subtype or event.get("thread_ts"):
            return {"status": "ignored"}
            
        # Check if it's the right channel
        if settings.SLACK_CHANNEL_ID and channel != settings.SLACK_CHANNEL_ID:
            return {"status": "ignored"}
            
        # Validate message format
        if SlackMessageValidator.is_valid_start_report(text):
            logger.info(f"Valid start report received from user {user} in channel {channel}")
            
            # Trigger attendance automation in background via Celery
            from app.workers.celery_worker import process_attendance_task
            process_attendance_task.delay(user, event_id, channel)
            
            return {"status": "processing"}
        else:
            logger.debug(f"Invalid message format from user {user}")
            
    return {"status": "ok"}
