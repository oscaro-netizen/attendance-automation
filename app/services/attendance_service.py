"""
Workday automation executed inside the Celery worker.

Two entry points mirror the two Slack commands:

    process_attendance -> start the workday in MarsOS
    process_logout     -> end the workday in MarsOS

Both are idempotent on `slack_event_id` and both record an `attendance_logs`
row for every outcome, so a Slack redelivery or a manual re-run never performs
the action twice and every attempt is auditable.

Error policy: *expected* failures (unknown employee, missing credentials, MarsOS
automation not succeeding) are handled here -- logged to the database and
reported to the employee in Slack -- and do not propagate. Anything genuinely
unexpected (database unavailable, misconfiguration) is allowed to propagate so
Celery's retry policy can act on it.
"""
import time
from typing import Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.marsos.factory import get_attendance_provider
from app.marsos.provider import AttendanceProvider
from app.models.models import AttendanceStatus, Employee
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import AttendanceLogCreate
from app.slack.client import SlackClient
from app.utils.time import local_today, to_local_display, utc_now


class AttendanceService:
    def __init__(self, db: AsyncSession, slack_client: Optional[SlackClient] = None):
        self.db = db
        self.emp_repo = EmployeeRepository(db)
        self.att_repo = AttendanceRepository(db)
        self.slack_client = slack_client or SlackClient()

    # --- Shared preconditions -------------------------------------------------

    async def _already_processed(self, slack_event_id: Optional[str]) -> bool:
        if not slack_event_id:
            return False
        existing = await self.att_repo.get_log_by_event_id(slack_event_id)
        if existing:
            logger.info(f"Slack event {slack_event_id} already processed. Skipping.")
            return True
        return False

    async def _resolve_employee(self, slack_user_id: str, channel_id: Optional[str]) -> Optional[Employee]:
        employee = await self.emp_repo.get_by_slack_id(slack_user_id)
        if employee is None:
            logger.error(f"Employee not found for Slack ID: {slack_user_id}")
            if channel_id:
                await self.slack_client.send_unregistered_reply(channel_id, slack_user_id)
        return employee

    def _resolve_password(self, employee: Employee) -> Tuple[Optional[str], Optional[str]]:
        """Returns `(password, failure_reason)`; exactly one is non-None."""
        if not employee.marsos_password_encrypted:
            logger.error(f"No password stored for employee {employee.marsos_email}")
            return None, "Missing credentials"
        try:
            return decrypt_password(employee.marsos_password_encrypted), None
        except CredentialDecryptionError:
            logger.error(f"Stored password for {employee.marsos_email} could not be decrypted")
            return None, "Undecryptable credentials"

    async def _release(self, provider: AttendanceProvider) -> None:
        """
        Releases provider resources without ever raising.

        This runs in a `finally` block: an exception escaping here would mask the
        real error and, on the success path, turn a completed workday start into
        a Celery retry.
        """
        try:
            await provider.close()
        except Exception as exc:
            logger.warning(f"Error releasing attendance provider: {exc}")

    # --- Start of workday -----------------------------------------------------

    async def process_attendance(
        self,
        slack_user_id: str,
        slack_event_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        if await self._already_processed(slack_event_id):
            return

        employee = await self._resolve_employee(slack_user_id, channel_id)
        if employee is None:
            return

        # Already started today?
        existing_log = await self.att_repo.get_successful_start_for_day(employee.id, local_today())
        if existing_log:
            logger.info(f"Attendance already started today for {employee.marsos_email}")
            await self.att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=utc_now(),
                slack_event_id=slack_event_id,
                started=False,
                status=AttendanceStatus.DUPLICATE,
                failure_reason="Already started today",
            ))
            if channel_id:
                await self.slack_client.send_duplicate_reply(channel_id, slack_user_id)
            return

        password, credential_error = self._resolve_password(employee)
        if password is None:
            await self.att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=utc_now(),
                slack_event_id=slack_event_id,
                started=False,
                status=AttendanceStatus.FAILURE,
                failure_reason=credential_error,
            ))
            if channel_id:
                await self.slack_client.send_credentials_error_reply(channel_id, slack_user_id)
            return

        provider = get_attendance_provider()
        start_time = time.time()
        success = False
        failure_reason: Optional[str] = None

        try:
            if await provider.login(employee.marsos_email, password):
                success = await provider.start_attendance(employee.marsos_employee_id)
                failure_reason = None if success else "Could not start workday in MarsOS"
            else:
                failure_reason = "MarsOS login failed"
        except Exception as e:
            logger.exception(f"Automation error while starting attendance: {e}")
            failure_reason = f"Automation error: {e}"
        finally:
            await self._release(provider)

        duration = time.time() - start_time
        now = utc_now()

        await self.att_repo.create_log(AttendanceLogCreate(
            employee_id=employee.id,
            date=now,
            slack_event_id=slack_event_id,
            started=success,
            started_at=now if success else None,
            status=AttendanceStatus.SUCCESS if success else AttendanceStatus.FAILURE,
            failure_reason=failure_reason,
            response_time=duration,
        ))

        if channel_id:
            if success:
                await self.slack_client.send_success_reply(channel_id, slack_user_id, to_local_display(now))
            else:
                await self.slack_client.send_failure_reply(channel_id, slack_user_id)

    # --- End of workday ---------------------------------------------------------

    async def process_logout(
        self,
        slack_user_id: str,
        slack_event_id: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> None:
        """Handles the `\\end` command: ends the workday in MarsOS."""
        logger.info(f"Processing end-of-workday for user {slack_user_id}")

        # The end path is idempotent on the same terms as the start path; without
        # this a Slack redelivery would drive a second browser session.
        if await self._already_processed(slack_event_id):
            return

        employee = await self._resolve_employee(slack_user_id, channel_id)
        if employee is None:
            return

        password, credential_error = self._resolve_password(employee)
        if password is None:
            await self.att_repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=utc_now(),
                slack_event_id=slack_event_id,
                started=False,
                status=AttendanceStatus.END_FAILURE,
                failure_reason=credential_error,
            ))
            if channel_id:
                await self.slack_client.send_credentials_error_reply(channel_id, slack_user_id)
            return

        provider = get_attendance_provider()
        start_time = time.time()
        success = False
        failure_reason: Optional[str] = None

        try:
            if await provider.login(employee.marsos_email, password):
                success = await provider.end_attendance(employee.marsos_employee_id)
                failure_reason = None if success else "Could not end workday in MarsOS"
            else:
                failure_reason = "MarsOS login failed"
        except Exception as e:
            logger.exception(f"Automation error while ending attendance: {e}")
            failure_reason = f"Automation error: {e}"
        finally:
            await self._release(provider)

        duration = time.time() - start_time
        now = utc_now()

        await self.att_repo.create_log(AttendanceLogCreate(
            employee_id=employee.id,
            date=now,
            slack_event_id=slack_event_id,
            started=False,
            status=AttendanceStatus.END_SUCCESS if success else AttendanceStatus.END_FAILURE,
            failure_reason=failure_reason,
            response_time=duration,
        ))

        if channel_id:
            if success:
                await self.slack_client.send_end_success_reply(channel_id, slack_user_id, to_local_display(now))
            else:
                await self.slack_client.send_end_failure_reply(channel_id, slack_user_id)
