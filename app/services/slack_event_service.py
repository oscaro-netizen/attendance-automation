"""
Business logic for the Slack Events API processing pipeline.

`app.api.slack_events` is a thin controller responsible only for HTTP
concerns (signature verification, JSON/schema parsing, URL verification,
and translating a `SlackEventResult` into an HTTP response). Every
decision about *what to do* with a validated event lives here, so it can
be unit tested without spinning up FastAPI, Celery, or Redis.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.slack_schemas import SlackEventEnvelope
from app.slack.client import SlackClient
from app.slack.event_deduplicator import SlackEventDeduplicator
from app.slack.validator import SlackMessageValidator
from app.workers.celery_worker import process_attendance_task

# Event types this pipeline acts on. Any other event type subscribed to in
# the Slack app configuration (e.g. `app_mention`, `reaction_added`) is
# accepted by signature verification but intentionally ignored here.
SUPPORTED_EVENT_TYPES = {"message"}

# Message subtypes that must never trigger attendance automation:
# bot-posted messages, edits, deletions, and channel membership churn.
IGNORED_MESSAGE_SUBTYPES = {
    "bot_message",
    "message_changed",
    "message_deleted",
    "message_replied",
    "channel_join",
    "channel_leave",
    "file_share",
}


class SlackEventOutcome(str, Enum):
    QUEUED = "queued"
    IGNORED_BOT_EVENT = "ignored_bot_event"
    IGNORED_UNSUPPORTED_EVENT = "ignored_unsupported_event"
    IGNORED_MESSAGE_SUBTYPE = "ignored_message_subtype"
    IGNORED_WRONG_CHANNEL = "ignored_wrong_channel"
    IGNORED_INVALID_FORMAT = "ignored_invalid_format"
    IGNORED_MISSING_EVENT_ID = "ignored_missing_event_id"
    DUPLICATE_EVENT = "duplicate_event"
    EMPLOYEE_NOT_REGISTERED = "employee_not_registered"


class SlackEventQueueError(Exception):
    """Raised when a validated, actionable event could not be enqueued to Celery."""


@dataclass(frozen=True)
class SlackEventResult:
    outcome: SlackEventOutcome
    celery_task_id: Optional[str] = None
    detail: Optional[str] = None


class SlackEventService:
    """
    Orchestrates the post-validation Slack event pipeline:

        Ignore Bot Events
          -> Ignore Unsupported Events
          -> Prevent Duplicate Events
          -> Resolve Employee
          -> Queue Celery Task

    Playwright automation is never invoked here or anywhere in the FastAPI
    process -- only a Celery task signature is dispatched, and the worker
    process owns execution.
    """

    def __init__(
        self,
        db: AsyncSession,
        deduplicator: SlackEventDeduplicator,
        employee_repo: Optional[EmployeeRepository] = None,
        slack_client: Optional[SlackClient] = None,
    ):
        self._db = db
        self._deduplicator = deduplicator
        self._employee_repo = employee_repo or EmployeeRepository(db)
        self._slack_client = slack_client or SlackClient()

    async def process_event(self, envelope: SlackEventEnvelope, request_id: str) -> SlackEventResult:
        log = logger.bind(request_id=request_id, event_id=envelope.event_id)
        event = envelope.event

        if event is None:
            log.warning("Slack event_callback payload is missing its 'event' object")
            return SlackEventResult(SlackEventOutcome.IGNORED_UNSUPPORTED_EVENT, detail="missing_event_object")

        log = log.bind(user_id=event.user)

        # --- Ignore Bot Events -------------------------------------------------
        # A `bot_id` on the event, or the `bot_message` subtype, indicates the
        # message was posted by a bot (including our own bot replying), which
        # must never re-trigger automation.
        if event.bot_id is not None or event.subtype == "bot_message":
            log.debug("Ignoring bot-authored Slack event")
            return SlackEventResult(SlackEventOutcome.IGNORED_BOT_EVENT)

        # --- Ignore Unsupported Events ------------------------------------------
        if event.type not in SUPPORTED_EVENT_TYPES:
            log.debug(f"Ignoring unsupported Slack event type: {event.type}")
            return SlackEventResult(SlackEventOutcome.IGNORED_UNSUPPORTED_EVENT, detail=event.type)

        if event.subtype in IGNORED_MESSAGE_SUBTYPES or event.thread_ts is not None:
            log.debug(f"Ignoring message subtype/thread reply: subtype={event.subtype}")
            return SlackEventResult(SlackEventOutcome.IGNORED_MESSAGE_SUBTYPE, detail=event.subtype)

        if settings.SLACK_CHANNEL_ID and event.channel != settings.SLACK_CHANNEL_ID:
            log.debug(f"Ignoring event from unmonitored channel: {event.channel}")
            return SlackEventResult(SlackEventOutcome.IGNORED_WRONG_CHANNEL, detail=event.channel)

        if not SlackMessageValidator.is_valid_start_report(event.text):
            log.debug("Ignoring message that does not match the expected start-report format")
            return SlackEventResult(SlackEventOutcome.IGNORED_INVALID_FORMAT)

        # --- Prevent Duplicate Events --------------------------------------------
        # Every actionable event must carry Slack's event_id; without it we
        # cannot guarantee idempotency, so we refuse to queue rather than
        # risk double-processing.
        if not envelope.event_id:
            log.error("Refusing to process event_callback with no event_id (cannot guarantee idempotency)")
            return SlackEventResult(SlackEventOutcome.IGNORED_MISSING_EVENT_ID)

        if await self._deduplicator.is_duplicate(envelope.event_id):
            log.info("Duplicate Slack event suppressed; no task will be queued")
            return SlackEventResult(SlackEventOutcome.DUPLICATE_EVENT)

        # --- Resolve Employee -----------------------------------------------------
        employee = await self._employee_repo.get_by_slack_id(event.user)
        if employee is None:
            log.warning(f"No registered employee for Slack user_id={event.user}")
            if event.channel:
                await self._slack_client.send_unregistered_reply(event.channel, event.user)
            return SlackEventResult(SlackEventOutcome.EMPLOYEE_NOT_REGISTERED)

        # --- Queue Celery Task ------------------------------------------------------
        # Attendance automation (Playwright) runs exclusively in the Celery
        # worker process. FastAPI's only responsibility is dispatch.
        try:
            task = process_attendance_task.delay(event.user, envelope.event_id, event.channel)
        except Exception as exc:
            log.exception("Failed to enqueue Celery task for Slack event")
            raise SlackEventQueueError(str(exc)) from exc

        log.bind(celery_task_id=task.id).info("Queued attendance automation task")
        return SlackEventResult(SlackEventOutcome.QUEUED, celery_task_id=task.id)
