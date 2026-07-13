from celery import Celery
from app.core.config import settings
from app.marsos.factory import get_attendance_provider
from app.database.session import AsyncSessionLocal
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.schemas import AttendanceLogCreate
from datetime import datetime
from loguru import logger
import asyncio
import time

celery_app = Celery("attendance_tasks", broker=settings.REDIS_URL)

async def run_attendance_automation(slack_user_id: str):
    async with AsyncSessionLocal() as db:
        emp_repo = EmployeeRepository(db)
        att_repo = AttendanceRepository(db)
        
        employee = await emp_repo.get_by_slack_id(slack_user_id)
        if not employee:
            logger.error(f"Employee not found for Slack ID: {slack_user_id}")
            return
            
        # Check for duplicate
        today = datetime.now().date()
        existing_log = await att_repo.get_log_for_day(employee.id, today)
        if existing_log:
            logger.info(f"Attendance already started today for {employee.marsos_email}")
            await att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=datetime.now(),
                started=False,
                status="duplicate",
                failure_reason="Already started today"
            ))
            # Reply to Slack (implement slack client call here)
            return

        # Start automation
        provider = get_attendance_provider()
        start_time = time.time()
        
        # Note: In a real scenario, you'd need employee credentials or a service account
        # For this implementation, we assume the provider handles it or we have them stored securely
        success = await provider.login(employee.marsos_email, "SECURE_PASSWORD_OR_TOKEN")
        
        if success:
            success = await provider.start_attendance(employee.marsos_employee_id)
            await provider.logout()
            
        duration = time.time() - start_time
        
        status = "success" if success else "failure"
        await att_repo.create_log(AttendanceLogCreate(
            employee_id=employee.id,
            date=datetime.now(),
            started=success,
            started_at=datetime.now() if success else None,
            status=status,
            failure_reason=None if success else "Automation failed",
            response_time=duration
        ))
        
        # Reply to Slack (implement slack client call here)

@celery_app.task(name="process_attendance")
def process_attendance_task(slack_user_id: str):
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(run_attendance_automation(slack_user_id))
