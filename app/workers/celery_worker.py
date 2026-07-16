from celery import Celery
from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.services.attendance_service import AttendanceService
from loguru import logger
import asyncio

celery_app = Celery("attendance_tasks", broker=settings.REDIS_URL)

# Configure Celery to handle retries and serialization
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

async def run_attendance_automation(slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    async with AsyncSessionLocal() as db:
        service = AttendanceService(db)
        await service.process_attendance(slack_user_id, slack_event_id, channel_id)

@celery_app.task(
    name="process_attendance",
    bind=True,
    max_retries=3,
    default_retry_delay=60, # 1 minute
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600, # 10 minutes
    retry_jitter=True
)
def process_attendance_task(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    """
    Celery task to trigger attendance automation with retries.
    """
    logger.info(f"Starting attendance task for user: {slack_user_id}, event: {slack_event_id}")
    try:
        # Check if a loop is already running
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        return loop.run_until_complete(run_attendance_automation(slack_user_id, slack_event_id, channel_id))
    except Exception as exc:
        logger.error(f"Task failed for user {slack_user_id}: {exc}")
        # Re-raise to trigger Celery's autoretry_for
        raise exc
