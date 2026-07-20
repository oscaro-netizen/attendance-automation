"""Behaviour of `AttendanceService.process_attendance` (the `\\end` counterpart
lives in test_attendance_service_end.py)."""
import pytest

from app.models.models import AttendanceStatus
from app.repositories.attendance_repository import AttendanceRepository
from app.schemas.schemas import AttendanceLogCreate
from app.services.attendance_service import AttendanceService
from app.utils.time import utc_now
from tests.factories import FakeProvider, FakeSlackClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def slack():
    return FakeSlackClient()


@pytest.fixture
def service(db_session, slack):
    return AttendanceService(db_session, slack_client=slack)


def use_provider(monkeypatch, provider):
    monkeypatch.setattr(
        "app.services.attendance_service.get_attendance_provider",
        lambda: provider,
    )
    return provider


async def latest_log(db_session):
    logs = await AttendanceRepository(db_session).list_logs()
    return logs[0]


class TestHappyPath:
    async def test_starts_attendance_logs_success_and_replies(
        self, service, db_session, employee, slack, monkeypatch
    ):
        provider = use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        assert provider.calls[:2] == ["login", "start_attendance"]
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.SUCCESS
        assert log.started is True
        assert log.started_at is not None
        assert log.response_time is not None
        assert slack.kinds == ["success"]

    async def test_releases_the_browser_exactly_once_on_success(
        self, service, employee, monkeypatch
    ):
        """
        Regression: `logout()` was called both inside the try block and again in
        `finally`, so the second close raised on an already-closed browser and
        turned a successful start into a Celery retry.
        """
        provider = use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        assert provider.close_count == 1

    async def test_reports_the_start_time_to_slack(self, service, employee, slack, monkeypatch):
        use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        assert slack.sent[0]["start_time"]


class TestIdempotency:
    async def test_a_replayed_event_id_does_not_run_automation_twice(
        self, service, db_session, employee, monkeypatch
    ):
        first = use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_SAME", "C_TEST")

        second = use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_SAME", "C_TEST")

        assert first.calls.count("start_attendance") == 1
        assert second.calls == []

    async def test_a_second_start_on_the_same_day_is_recorded_as_a_duplicate(
        self, service, db_session, employee, slack, monkeypatch
    ):
        use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        provider = use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_2", "C_TEST")

        assert provider.calls == []  # never touched the browser
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.DUPLICATE
        assert slack.kinds == ["success", "duplicate"]

    async def test_two_success_rows_on_one_day_do_not_raise(
        self, service, db_session, employee, slack, monkeypatch
    ):
        """
        Regression: the day lookup used `scalar_one_or_none()`, which raised
        `MultipleResultsFound` once a second success row existed for the day.
        """
        repo = AttendanceRepository(db_session)
        for event_id in ("Ev_A", "Ev_B"):
            await repo.create_log(AttendanceLogCreate(
                employee_id=employee.id,
                date=utc_now(),
                slack_event_id=event_id,
                started=True,
                status=AttendanceStatus.SUCCESS,
            ))

        use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_C", "C_TEST")

        assert slack.kinds == ["duplicate"]

    async def test_a_failed_start_does_not_block_a_later_retry(
        self, service, db_session, employee, monkeypatch
    ):
        use_provider(monkeypatch, FakeProvider(start_result=False))
        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        retry = use_provider(monkeypatch, FakeProvider())
        await service.process_attendance(employee.slack_user_id, "Ev_2", "C_TEST")

        assert "start_attendance" in retry.calls
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.SUCCESS


class TestFailureHandling:
    async def test_unknown_employee_is_told_they_are_not_registered(self, service, slack):
        await service.process_attendance("U_NOT_REGISTERED", "Ev_1", "C_TEST")
        assert slack.kinds == ["unregistered"]

    async def test_unknown_employee_writes_no_log(self, service, db_session):
        await service.process_attendance("U_NOT_REGISTERED", "Ev_1", "C_TEST")
        assert await AttendanceRepository(db_session).list_logs() == []

    async def test_missing_credentials_are_logged_and_reported(
        self, service, db_session, employee, slack, monkeypatch
    ):
        employee.marsos_password_encrypted = None
        await db_session.commit()
        provider = use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        assert provider.calls == []
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.FAILURE
        assert log.failure_reason == "Missing credentials"
        assert slack.kinds == ["credentials_error"]

    async def test_a_password_encrypted_with_another_key_is_reported_distinctly(
        self, service, db_session, employee, slack, monkeypatch
    ):
        """
        Regression: an ephemeral encryption key used to make every stored
        password decrypt into garbage; it must surface as its own failure
        reason rather than looking like an absent password.
        """
        from cryptography.fernet import Fernet

        other_key_cipher = Fernet(Fernet.generate_key())
        employee.marsos_password_encrypted = other_key_cipher.encrypt(b"secret").decode()
        await db_session.commit()
        use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        log = await latest_log(db_session)
        assert log.failure_reason == "Undecryptable credentials"
        assert slack.kinds == ["credentials_error"]

    async def test_a_failed_login_is_logged_as_a_failure(
        self, service, db_session, employee, slack, monkeypatch
    ):
        provider = use_provider(monkeypatch, FakeProvider(login_result=False))

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        assert "start_attendance" not in provider.calls
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.FAILURE
        assert log.failure_reason == "MarsOS login failed"
        assert log.started is False
        assert slack.kinds == ["failure"]

    async def test_an_exception_inside_automation_is_contained(
        self, service, db_session, employee, slack, monkeypatch
    ):
        provider = use_provider(monkeypatch, FakeProvider(raise_on="start_attendance"))

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.FAILURE
        assert "Automation error" in log.failure_reason
        assert provider.close_count == 1
        assert slack.kinds == ["failure"]

    async def test_an_error_while_closing_does_not_fail_a_successful_run(
        self, service, db_session, employee, slack, monkeypatch
    ):
        use_provider(monkeypatch, FakeProvider(raise_on="close"))

        await service.process_attendance(employee.slack_user_id, "Ev_1", "C_TEST")

        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.SUCCESS
        assert slack.kinds == ["success"]


class TestChannelless:
    async def test_no_slack_reply_is_attempted_without_a_channel(
        self, service, db_session, employee, slack, monkeypatch
    ):
        """The manual retry endpoint queues work with no originating channel."""
        use_provider(monkeypatch, FakeProvider())

        await service.process_attendance(employee.slack_user_id, None, None)

        assert slack.sent == []
        log = await latest_log(db_session)
        assert log.status == AttendanceStatus.SUCCESS
