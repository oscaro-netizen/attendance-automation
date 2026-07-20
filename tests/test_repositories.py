"""Repository-level guarantees, chiefly the idempotency constraint."""
from datetime import timedelta

import pytest

from app.models.models import AttendanceStatus
from app.repositories.attendance_repository import AttendanceRepository
from app.repositories.employee_repository import EmployeeRepository
from app.schemas.schemas import AttendanceLogCreate, EmployeeCreate
from app.utils.time import local_today, utc_now

pytestmark = pytest.mark.asyncio


def log(employee_id, event_id=None, status=AttendanceStatus.SUCCESS, when=None):
    return AttendanceLogCreate(
        employee_id=employee_id,
        date=when or utc_now(),
        slack_event_id=event_id,
        started=status == AttendanceStatus.SUCCESS,
        status=status,
    )


class TestAttendanceRepository:
    async def test_finds_a_successful_start_for_today(self, db_session, employee):
        repo = AttendanceRepository(db_session)
        await repo.create_log(log(employee.id, "Ev_1"))

        assert await repo.get_successful_start_for_day(employee.id, local_today()) is not None

    async def test_ignores_failed_and_duplicate_rows(self, db_session, employee):
        repo = AttendanceRepository(db_session)
        await repo.create_log(log(employee.id, "Ev_F", AttendanceStatus.FAILURE))
        await repo.create_log(log(employee.id, "Ev_D", AttendanceStatus.DUPLICATE))
        await repo.create_log(log(employee.id, "Ev_E", AttendanceStatus.END_SUCCESS))

        assert await repo.get_successful_start_for_day(employee.id, local_today()) is None

    async def test_ignores_another_employees_start(self, db_session, employee):
        repo = AttendanceRepository(db_session)
        other = await EmployeeRepository(db_session).create(EmployeeCreate(
            slack_user_id="U_OTHER",
            slack_username="other",
            marsos_email="other@example.com",
            marsos_employee_id="EMP_OTHER",
            marsos_password="pw",
        ))
        await repo.create_log(log(other.id, "Ev_1"))

        assert await repo.get_successful_start_for_day(employee.id, local_today()) is None

    async def test_ignores_a_start_from_a_different_day(self, db_session, employee):
        repo = AttendanceRepository(db_session)
        await repo.create_log(log(employee.id, "Ev_OLD", when=utc_now() - timedelta(days=2)))

        assert await repo.get_successful_start_for_day(employee.id, local_today()) is None

    async def test_two_success_rows_in_one_day_return_the_earliest_not_an_error(
        self, db_session, employee
    ):
        """Regression: `scalar_one_or_none()` raised `MultipleResultsFound` here."""
        repo = AttendanceRepository(db_session)
        earlier = utc_now() - timedelta(minutes=30)
        await repo.create_log(log(employee.id, "Ev_2"))
        await repo.create_log(log(employee.id, "Ev_1", when=earlier))

        found = await repo.get_successful_start_for_day(employee.id, local_today())
        assert found.slack_event_id == "Ev_1"

    async def test_a_duplicate_event_id_is_absorbed_and_returns_the_existing_row(
        self, db_session, employee
    ):
        """
        A Slack redelivery racing another worker hits the unique constraint. That
        is the constraint working, not an error worth failing the whole task over.
        """
        repo = AttendanceRepository(db_session)
        first = await repo.create_log(log(employee.id, "Ev_SAME"))
        second = await repo.create_log(log(employee.id, "Ev_SAME", AttendanceStatus.FAILURE))

        assert second is not None
        assert second.id == first.id
        assert len(await repo.list_logs()) == 1

    async def test_rows_without_an_event_id_are_not_deduplicated(self, db_session, employee):
        """Manual re-runs carry no event id and must each be recorded."""
        repo = AttendanceRepository(db_session)
        await repo.create_log(log(employee.id, None))
        await repo.create_log(log(employee.id, None))

        assert len(await repo.list_logs()) == 2

    async def test_lists_logs_newest_first(self, db_session, employee):
        repo = AttendanceRepository(db_session)
        await repo.create_log(log(employee.id, "Ev_1"))
        await repo.create_log(log(employee.id, "Ev_2"))

        logs = await repo.list_logs()
        assert [entry.slack_event_id for entry in logs][0] in {"Ev_1", "Ev_2"}
        assert len(logs) == 2


class TestEmployeeRepository:
    async def test_stores_the_password_encrypted_not_in_plaintext(self, db_session):
        created = await EmployeeRepository(db_session).create(EmployeeCreate(
            slack_user_id="U_NEW",
            slack_username="new",
            marsos_email="new@example.com",
            marsos_employee_id="EMP_NEW",
            marsos_password="hunter2",
        ))

        assert created.marsos_password_encrypted
        assert "hunter2" not in created.marsos_password_encrypted

    async def test_looks_an_employee_up_by_slack_id(self, db_session, employee):
        found = await EmployeeRepository(db_session).get_by_slack_id(employee.slack_user_id)
        assert found.marsos_email == employee.marsos_email

    async def test_returns_none_for_an_unknown_slack_id(self, db_session):
        assert await EmployeeRepository(db_session).get_by_slack_id("U_NOBODY") is None
