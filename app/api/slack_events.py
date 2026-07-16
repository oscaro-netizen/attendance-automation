import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
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


@router.post("/slack/events", dependencies=[Depends(verify_slack_signature)])
async def slack_events(
    request: Request,
    db: AsyncSession = Depends(get_db),
    deduplicator: SlackEventDeduplicator = Depends(get_event_deduplicator),
):
    """
    Slack Events API webhook.

    By the time this handler runs, `verify_slack_signature` has already
    confirmed the request is authentically from Slack and within the
    replay-protection time window. This handler is responsible for:

      1. Parsing and schema-validating the JSON body.
      2. Handling the `url_verification` handshake.
      3. Delegating `event_callback` payloads to `SlackEventService`.
      4. Returning HTTP 200 as fast as possible in every non-error case,
         so Slack does not treat the delivery as failed and retry it.

    No Playwright automation ever runs on this request path -- actionable
    events are handed off to Celery and this handler returns immediately.
    """
    request_id = uuid.uuid4().hex
    log = logger.bind(request_id=request_id)

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        log.warning("Rejected Slack request: malformed JSON body")
        raise HTTPException(status_code=400, detail="Malformed JSON payload")

    try:
        envelope = SlackEventEnvelope.model_validate(payload)
    except ValidationError as exc:
        log.warning(f"Rejected Slack request: payload failed schema validation ({exc.error_count()} error(s))")
        raise HTTPException(status_code=400, detail="Invalid Slack event payload")

    # --- Handle URL Verification Challenge ---------------------------------
    if envelope.is_url_verification:
        if not envelope.challenge:
            log.warning("Rejected Slack url_verification request: missing challenge")
            raise HTTPException(status_code=400, detail="Missing challenge in URL verification payload")
        log.info("Handled Slack URL verification challenge")
        return {"challenge": envelope.challenge}

    # Anything that is neither a challenge nor an event_callback (e.g. a
    # future payload type we haven't subscribed to) is acknowledged and
    # dropped rather than erroring, since erroring would cause Slack to
    # retry a payload we will never be able to act on.
    if not envelope.is_event_callback:
        log.debug(f"Ignoring unsupported Slack payload type: {envelope.type}")
        return {"status": "ignored", "detail": "unsupported_payload_type"}

    service = SlackEventService(db=db, deduplicator=deduplicator)

    try:
        result = await service.process_event(envelope, request_id=request_id)
    except SlackEventQueueError as exc:
        log.error(f"Slack event validated but could not be queued: {exc}")
        # 5xx signals Slack to retry delivery once the queue is healthy
        # again, rather than silently dropping a legitimate event.
        raise HTTPException(status_code=503, detail="Unable to queue attendance task") from exc

    log.bind(
        event_id=envelope.event_id,
        user_id=envelope.event.user if envelope.event else None,
        outcome=result.outcome.value,
        celery_task_id=result.celery_task_id,
    ).info("Slack event processed")

    return {"status": result.outcome.value, "detail": result.detail}
