import asyncio
from typing import Optional

from celery import Celery
from loguru import logger

from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.services.attendance_service import AttendanceService

# Define celery_app to match docker-compose and keep app as an alias
celery_app = Celery("attendance_tasks", broker=settings.REDIS_URL)
app = celery_app

# Configure Celery to handle retries and serialization
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)


def _run(coro):
    """
    Runs a coroutine from a synchronous Celery task.

    `asyncio.run` creates and disposes of a fresh event loop per task. The
    previous `asyncio.get_event_loop()` approach reused a loop across tasks in
    the same worker process, which raises `RuntimeError: Event loop is closed`
    once anything (such as Playwright teardown) closes it, and is deprecated in
    modern Python besides.
    """
    return asyncio.run(coro)


# Helper to run async functions in Celery
async def run_attendance_automation(
    slack_user_id: str,
    slack_event_id: Optional[str] = None,
    channel_id: Optional[str] = None,
):
    async with AsyncSessionLocal() as db:
        service = AttendanceService(db)
        await service.process_attendance(slack_user_id, slack_event_id, channel_id)


async def run_logout_automation(
    slack_user_id: str,
    slack_event_id: Optional[str] = None,
    channel_id: Optional[str] = None,
):
    async with AsyncSessionLocal() as db:
        service = AttendanceService(db)
        await service.process_logout(slack_user_id, slack_event_id, channel_id)


# `AttendanceService` handles every expected failure itself (logging the outcome
# and replying in Slack), so an exception reaching Celery means something
# genuinely unexpected happened -- exactly the case worth retrying. Retries are
# safe because both entry points are idempotent on `slack_event_id`.
@app.task(
    name="process_attendance",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_attendance_task(
    self,
    slack_user_id: str,
    slack_event_id: Optional[str] = None,
    channel_id: Optional[str] = None,
):
    logger.info(f"Starting attendance task for user: {slack_user_id}")
    return _run(run_attendance_automation(slack_user_id, slack_event_id, channel_id))


@app.task(
    name="process_logout_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_logout_task(
    self,
    slack_user_id: str,
    slack_event_id: Optional[str] = None,
    channel_id: Optional[str] = None,
):
    logger.info(f"Starting end-of-workday task (\\end) for user: {slack_user_id}")
    return _run(run_logout_automation(slack_user_id, slack_event_id, channel_id))
