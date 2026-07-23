"""
Slack webhook -> TimeTrack attendance.

A start report clocks the sender in; a completed-work report clocks them out. Nothing is
recorded here and nothing is posted back to Slack -- TimeTrack is the system of
record, and the only state this service keeps is each employee's token.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status

from app.config import settings
from app.messages import Action, classify
from app.slack_verify import verify_slack_signature
from app.store import get_token, init_db
from app.timetrack import TimeTrackAuthError, TimeTrackClient, TimeTrackError, is_clocked_in

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


_docs = settings.ENABLE_API_DOCS
app = FastAPI(
    title="Attendance Automation",
    lifespan=lifespan,
    openapi_url="/openapi.json" if _docs else None,
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
)

# Message subtypes that must never trigger attendance: bot posts, edits,
# deletions, and channel membership churn.
IGNORED_SUBTYPES = {
    "bot_message",
    "message_changed",
    "message_deleted",
    "message_replied",
    "channel_join",
    "channel_leave",
    "file_share",
}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def run_action(slack_user_id: str, action: Action, token: str) -> None:
    """
    Performs the attendance action in TimeTrack.

    Runs after the webhook has already answered Slack, so nothing here can make
    Slack time out. Failures are logged; there is no reply to send.
    """
    client = TimeTrackClient(token)
    try:
        # TimeTrack's own view of the day is the idempotency guard: if the
        # employee is already in the desired state -- because Slack redelivered
        # the event, or they posted twice -- there is nothing to do.
        state = is_clocked_in(await client.today())
        if state is True and action is Action.CLOCK_IN:
            logger.info("%s is already clocked in; skipping", slack_user_id)
            return
        if state is False and action is Action.CLOCK_OUT:
            logger.info("%s is already clocked out; skipping", slack_user_id)
            return

        if action is Action.CLOCK_IN:
            await client.clock_in()
        else:
            await client.clock_out()

        logger.info("%s: %s succeeded", slack_user_id, action.value)

    except TimeTrackAuthError:
        logger.error("%s: TimeTrack rejected the token; it needs re-registering", slack_user_id)
    except TimeTrackError as exc:
        logger.error("%s: %s failed: %s", slack_user_id, action.value, exc)


@app.post("/slack/events", dependencies=[Depends(verify_slack_signature)])
async def slack_events(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed Slack payload")

    # Slack sends this once when the Request URL is saved.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    if payload.get("type") != "event_callback":
        return {"status": "ignored"}

    event = payload.get("event")
    if not isinstance(event, dict):
        return {"status": "ignored"}

    # Bot posts must never trigger automation.
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"status": "ignored"}

    if event.get("type") != "message":
        return {"status": "ignored"}

    if event.get("subtype") in IGNORED_SUBTYPES or event.get("thread_ts"):
        return {"status": "ignored"}

    if settings.SLACK_CHANNEL_ID and event.get("channel") != settings.SLACK_CHANNEL_ID:
        return {"status": "ignored"}

    action = classify(event.get("text"))
    if action is None:
        return {"status": "ignored"}

    slack_user_id = event.get("user")
    if not slack_user_id:
        return {"status": "ignored"}

    token = get_token(slack_user_id)
    if not token:
        logger.warning("No TimeTrack token registered for Slack user %s", slack_user_id)
        return {"status": "unregistered"}

    # Answer Slack now; do the work afterwards. Slack gives us 3 seconds and
    # retries if it does not get a 200, which would duplicate the request.
    background_tasks.add_task(run_action, slack_user_id, action, token)
    return {"status": "accepted", "action": action.value}
