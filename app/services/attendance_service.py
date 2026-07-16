from datetime import datetime
import time
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.employee_repository import EmployeeRepository
from app.repositories.attendance_repository import AttendanceRepository
from app.marsos.factory import get_attendance_provider
from app.slack.client import SlackClient
from app.schemas.schemas import AttendanceLogCreate
from app.utils.security import decrypt_password
from loguru import logger

class AttendanceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.emp_repo = EmployeeRepository(db)
        self.att_repo = AttendanceRepository(db)
        self.slack_client = SlackClient()

    async def process_attendance(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
        # Check idempotency
        if slack_event_id:
            existing_event = await self.att_repo.get_log_by_event_id(slack_event_id)
            if existing_event:
                logger.info(f"Slack event {slack_event_id} already processed. Skipping.")
                return

        employee = await self.emp_repo.get_by_slack_id(slack_user_id)
        if not employee:
            logger.error(f"Employee not found for Slack ID: {slack_user_id}")
            return
            
        # Check for duplicate
        today = datetime.now().date()
        existing_log = await self.att_repo.get_log_for_day(employee.id, today)
        if existing_log:
            logger.info(f"Attendance already started today for {employee.marsos_email}")
            await self.att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=datetime.now(),
                slack_event_id=slack_event_id,
                started=False,
                status="duplicate",
                failure_reason="Already started today"
            ))
            if channel_id:
                await self.slack_client.send_duplicate_reply(channel_id, slack_user_id)
            return

        # Start automation
        provider = get_attendance_provider()
        start_time = time.time()
        
        # Decrypt password for login
        password = decrypt_password(employee.marsos_password_encrypted) if employee.marsos_password_encrypted else None
        
        if not password:
            logger.error(f"No password found for employee {employee.marsos_email}")
            await self.att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=datetime.now(),
                slack_event_id=slack_event_id,
                started=False,
                status="failure",
                failure_reason="Missing credentials"
            ))
            if channel_id:
                await self.slack_client.send_failure_reply(channel_id, slack_user_id)
            return

        success = False
        try:
            success = await provider.login(employee.marsos_email, password)
            if success:
                success = await provider.start_attendance(employee.marsos_employee_id)
                await provider.logout()
        except Exception as e:
            logger.error(f"Automation error: {str(e)}")
            success = False
        finally:
            await provider.logout()
            
        duration = time.time() - start_time
        now = datetime.now()
        
        status = "success" if success else "failure"
        await self.att_repo.create_log(AttendanceLogCreate(
            employee_id=employee.id,
            date=now,
            slack_event_id=slack_event_id,
            started=success,
            started_at=now if success else None,
            status=status,
            failure_reason=None if success else "Automation failed",
            response_time=duration
        ))
        
        if channel_id:
            if success:
                start_time_str = now.strftime("%I:%M %p")
                await self.slack_client.send_success_reply(channel_id, slack_user_id, start_time_str)
            else:
                await self.slack_client.send_failure_reply(channel_id, slack_user_id)

    async def process_stop_attendance(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
        """
        Handles the DM-based end-of-day stop/clock-out message. Mirrors
        process_attendance's structure, but closes an existing open session
        rather than creating a new attendance_logs row.
        """
        # Check idempotency on the stop event specifically (separate from
        # the Start event's idempotency key on the same row).
        if slack_event_id:
            existing_stop_event = await self.att_repo.get_log_by_stop_event_id(slack_event_id)
            if existing_stop_event:
                logger.info(f"Slack stop event {slack_event_id} already processed. Skipping.")
                return

        employee = await self.emp_repo.get_by_slack_id(slack_user_id)
        if not employee:
            logger.error(f"Employee not found for Slack ID: {slack_user_id}")
            return

        today = datetime.now().date()
        active_log = await self.att_repo.get_active_log_for_day(employee.id, today)

        if not active_log:
            logger.info(f"No active start found today for {employee.marsos_email}; ignoring stop request")
            if channel_id:
                await self.slack_client.send_not_started_reply(channel_id, slack_user_id)
            return

        if active_log.ended:
            logger.info(f"Attendance already stopped today for {employee.marsos_email}")
            if channel_id:
                await self.slack_client.send_stop_duplicate_reply(channel_id, slack_user_id)
            return

        provider = get_attendance_provider()
        start_time = time.time()

        password = decrypt_password(employee.marsos_password_encrypted) if employee.marsos_password_encrypted else None

        if not password:
            logger.error(f"No password found for employee {employee.marsos_email}")
            await self.att_repo.update_log(
                active_log,
                stop_slack_event_id=slack_event_id,
                stop_status="failure",
                stop_failure_reason="Missing credentials",
            )
            if channel_id:
                await self.slack_client.send_stop_failure_reply(channel_id, slack_user_id)
            return

        success = False
        try:
            success = await provider.login(employee.marsos_email, password)
            if success:
                success = await provider.stop_attendance(employee.marsos_employee_id)
        except Exception as e:
            logger.error(f"Stop automation error: {str(e)}")
            success = False
        finally:
            await provider.logout()

        duration = time.time() - start_time
        now = datetime.now()

        await self.att_repo.update_log(
            active_log,
            ended=success,
            ended_at=now if success else None,
            stop_slack_event_id=slack_event_id,
            stop_status="success" if success else "failure",
            stop_failure_reason=None if success else "Automation failed",
            stop_response_time=duration,
        )

        if channel_id:
            if success:
                end_time_str = now.strftime("%I:%M %p")
                await self.slack_client.send_stop_success_reply(channel_id, slack_user_id, end_time_str)
            else:
                await self.slack_client.send_stop_failure_reply(channel_id, slack_user_id)
