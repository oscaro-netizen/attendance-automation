"""Behaviour of `AttendanceService.process_logout` -- the `\\end` command."""
import pytest

from app.models.models import AttendanceStatus
from app.repositories.attendance_repository import AttendanceRepository
from app.services.attendance_service import AttendanceService
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


async def test_ends_the_workday_logs_it_and_replies(
    service, db_session, employee, slack, monkeypatch
):
    provider = use_provider(monkeypatch, FakeProvider())

    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    assert provider.calls[:2] == ["login", "end_attendance"]
    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.END_SUCCESS
    assert slack.kinds == ["end_success"]


async def test_releases_the_browser_exactly_once(service, employee, monkeypatch):
    provider = use_provider(monkeypatch, FakeProvider())
    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")
    assert provider.close_count == 1


async def test_a_replayed_end_event_does_not_run_automation_twice(
    service, employee, monkeypatch
):
    """
    Regression: the `\\end` path had no idempotency check at all, so a Slack
    redelivery drove a second browser session.
    """
    first = use_provider(monkeypatch, FakeProvider())
    await service.process_logout(employee.slack_user_id, "Ev_SAME", "C_TEST")

    second = use_provider(monkeypatch, FakeProvider())
    await service.process_logout(employee.slack_user_id, "Ev_SAME", "C_TEST")

    assert first.calls.count("end_attendance") == 1
    assert second.calls == []


async def test_end_is_recorded_even_when_it_fails(
    service, db_session, employee, slack, monkeypatch
):
    use_provider(monkeypatch, FakeProvider(end_result=False))

    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.END_FAILURE
    assert log.failure_reason == "Could not end workday in MarsOS"
    assert slack.kinds == ["end_failure"]


async def test_a_failed_login_is_recorded_and_reported(
    service, db_session, employee, slack, monkeypatch
):
    provider = use_provider(monkeypatch, FakeProvider(login_result=False))

    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    assert "end_attendance" not in provider.calls
    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.END_FAILURE
    assert log.failure_reason == "MarsOS login failed"
    assert slack.kinds == ["end_failure"]


async def test_unknown_employee_is_told_they_are_not_registered(service, slack):
    await service.process_logout("U_NOT_REGISTERED", "Ev_END_1", "C_TEST")
    assert slack.kinds == ["unregistered"]


async def test_missing_credentials_are_logged_and_reported(
    service, db_session, employee, slack, monkeypatch
):
    employee.marsos_password_encrypted = None
    await db_session.commit()
    provider = use_provider(monkeypatch, FakeProvider())

    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    assert provider.calls == []
    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.END_FAILURE
    assert slack.kinds == ["credentials_error"]


async def test_an_exception_inside_automation_is_contained(
    service, db_session, employee, slack, monkeypatch
):
    provider = use_provider(monkeypatch, FakeProvider(raise_on="end_attendance"))

    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.END_FAILURE
    assert "Automation error" in log.failure_reason
    assert provider.close_count == 1


async def test_ending_a_workday_does_not_count_as_a_start_for_the_day(
    service, db_session, employee, slack, monkeypatch
):
    """An END row must not make a later start look like a duplicate."""
    use_provider(monkeypatch, FakeProvider())
    await service.process_logout(employee.slack_user_id, "Ev_END_1", "C_TEST")

    use_provider(monkeypatch, FakeProvider())
    await service.process_attendance(employee.slack_user_id, "Ev_START_1", "C_TEST")

    log = await latest_log(db_session)
    assert log.status == AttendanceStatus.SUCCESS
    assert slack.kinds == ["end_success", "success"]
