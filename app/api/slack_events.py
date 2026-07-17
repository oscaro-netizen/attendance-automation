from fastapi import APIRouter, Request, Depends, BackgroundTasks
from app.middleware.slack_verification import verify_slack_signature
from app.slack.validator import SlackMessageValidator
from app.core.config import settings
from loguru import logger
import json

router = APIRouter()

@router.post("/events", dependencies=[Depends(verify_slack_signature)])
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()

    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}
        
    event = data.get("event", {})
    event_type = event.get("type")
    
    # We listen for messages
    if event_type == "message":
        channel = event.get("channel")
        user = event.get("user")
        text = event.get("text", "").strip()
        subtype = event.get("subtype")
        event_id = data.get("event_id")
        
        # Ignore bot messages, edits, and deletions
        if subtype or event.get("thread_ts"):
            return {"status": "ignored"}

        # --- UPDATED CHANNEL LOGIC ---
        # Allow DMs (channel IDs starting with 'D') or the specific configured channel
        is_dm = channel.startswith('D')
        is_main_channel = settings.SLACK_CHANNEL_ID and channel == settings.SLACK_CHANNEL_ID
        
        if not (is_dm or is_main_channel):
            return {"status": "ignored"}
        # -----------------------------

        # Handle \end command (Works in DMs and Main Channel)
        if text == "\\end":
            logger.info(f"End workday request received from user {user} in {'DM' if is_dm else 'channel'}")
            from app.workers.celery_worker import process_logout_task
            process_logout_task.delay(user, event_id, channel)
            return {"status": "processing_end"}
            
        # Handle start report (Works in Main Channel)
        if SlackMessageValidator.is_valid_start_report(text):
            logger.info(f"Valid start report received from user {user}")
            from app.workers.celery_worker import process_attendance_task
            process_attendance_task.delay(user, event_id, channel)
            return {"status": "processing_start"}
            
    return {"status": "ok"}
