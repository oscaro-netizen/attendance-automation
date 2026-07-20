"""
HTTP controller for the Slack Events API.

Responsibilities are deliberately limited to HTTP concerns: signature
verification, payload parsing, the `url_verification` handshake, and mapping a
`SlackEventResult` onto a response body. All decision-making lives in
`app.services.slack_event_service`.

Slack retries any event it does not receive a 2xx for within 3 seconds, so this
handler always answers 200 for a well-formed, correctly signed payload -- even
when the event is ignored. Only a genuine server-side failure to enqueue work
returns 5xx, which is precisely the case where a Slack retry is useful.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.middleware.slack_verification import verify_slack_signature
from app.schemas.slack_schemas import SlackEventEnvelope
from app.services.slack_event_service import (
    SlackEventQueueError,
    SlackEventService,
)
from app.slack.event_deduplicator import SlackEventDeduplicator, get_event_deduplicator

router = APIRouter()


@router.post("/events", dependencies=[Depends(verify_slack_signature)])
async def slack_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
    deduplicator: SlackEventDeduplicator = Depends(get_event_deduplicator),
):
    request_id = str(uuid.uuid4())
    log = logger.bind(request_id=request_id)

    try:
        payload = await request.json()
    except ValueError:
        log.warning("Slack request body was not valid JSON")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    try:
        envelope = SlackEventEnvelope.model_validate(payload)
    except ValidationError as exc:
        log.warning(f"Slack payload failed schema validation: {exc.errors()}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Slack payload")

    # Handle URL verification challenge
    if envelope.is_url_verification:
        log.info("Responding to Slack url_verification challenge")
        return {"challenge": envelope.challenge}

    if not envelope.is_event_callback:
        log.debug(f"Ignoring non-event_callback payload of type {envelope.type}")
        return {"status": "ignored", "reason": "unsupported_payload_type"}

    service = SlackEventService(db=db, deduplicator=deduplicator)
    try:
        result = await service.process_event(envelope, request_id=request_id)
    except SlackEventQueueError as exc:
        # The event was valid and actionable but could not be handed to Celery.
        # A 5xx makes Slack redeliver it, which is the behaviour we want here.
        log.error(f"Could not enqueue Slack event: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not queue attendance automation; the event will be retried",
        )

    return {
        "status": result.outcome.value,
        "request_id": request_id,
        **({"task_id": result.celery_task_id} if result.celery_task_id else {}),
        **({"detail": result.detail} if result.detail else {}),
    }
