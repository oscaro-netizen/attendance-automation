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

    async def process_logout(self, slack_user_id: str, slack_event_id: str = None, channel_id: str = None):
        """
        Handles the logout process (\end) for a user.
        """
        logger.info(f"Processing logout for user {slack_user_id}")
        
        # 1. Get employee from database
        employee = await self.emp_repo.get_by_slack_id(slack_user_id)
        if not employee:
            logger.error(f"Employee {slack_user_id} not found in database")
            if channel_id:
                await self.slack_client.send_message(
                    channel=channel_id,
                    text=f"<@{slack_user_id}> ⚠️ You are not registered in the system. Please contact an admin."
                )
            return

        # 2. Initialize the MarsOS Provider
        provider = get_attendance_provider()
        
        # 3. Decrypt password
        password = decrypt_password(employee.marsos_password_encrypted) if employee.marsos_password_encrypted else None
        
        if not password:
            logger.error(f"No password found for employee {employee.marsos_email}")
            if channel_id:
                await self.slack_client.send_message(
                    channel=channel_id,
                    text=f"<@{slack_user_id}> ❌ Missing credentials. Cannot perform logout."
                )
            return
        
        success = False
        try:
            # 4. Login and Trigger Logout
            login_success = await provider.login(employee.marsos_email, password)
            if login_success:
                if hasattr(provider, "logout_attendance"):
                    success = await provider.logout_attendance(employee.marsos_employee_id)
                else:
                    success = True
                await provider.logout()
            else:
                if channel_id:
                    await self.slack_client.send_message(
                        channel=channel_id,
                        text=f"<@{slack_user_id}> ❌ Failed to log into MarsOS. Please check your credentials."
                    )
                return
        except Exception as e:
            logger.error(f"Error during logout process: {str(e)}")
            success = False
        finally:
            await provider.logout()

        # 5. Send response to Slack
        if channel_id:
            if success:
                await self.slack_client.send_message(
                    channel=channel_id,
                    text=f"✅ Workday ended successfully for <@{slack_user_id}>! See you next time. 👋"
                )
            else:
                await self.slack_client.send_message(
                    channel=channel_id,
                    text=f"<@{slack_user_id}> ⚠️ I couldn't find the 'End Workday' button. Are you sure you started your shift?"
                )
