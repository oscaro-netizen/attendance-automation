from celery import Celery
from app.core.config import settings
from app.database.session import AsyncSessionLocal
from app.services.attendance_service import AttendanceService
from loguru import logger
import asyncio

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

# Helper to run async functions in Celery
async def run_attendance_automation(slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    async with AsyncSessionLocal() as db:
        service = AttendanceService(db)
        await service.process_attendance(slack_user_id, slack_event_id, channel_id)

# NEW Helper for logout
async def run_logout_automation(slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    async with AsyncSessionLocal() as db:
        service = AttendanceService(db)
        await service.process_logout(slack_user_id, slack_event_id, channel_id)

@app.task(
    name="process_attendance",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def process_attendance_task(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    logger.info(f"Starting attendance task for user: {slack_user_id}")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(run_attendance_automation(slack_user_id, slack_event_id, channel_id))

# --- NEW: Logout Task ---
@app.task(
    name="process_logout_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True
)
def process_logout_task(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
    logger.info(f"Starting logout task (\\stop) for user: {slack_user_id}")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(run_logout_automation(slack_user_id, slack_event_id, channel_id))
