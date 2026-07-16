import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.attendance_service import AttendanceService
from app.models.models import Employee, AttendanceLog
from app.utils.security import encrypt_password


async def _make_employee(test_db_session: AsyncSession, slack_user_id: str, email: str, employee_id: str) -> Employee:
    employee = Employee(
        slack_user_id=slack_user_id,
        slack_username=slack_user_id.lower(),
        marsos_email=email,
        marsos_employee_id=employee_id,
        marsos_password_encrypted=encrypt_password("test_password"),
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)
    return employee


@pytest.mark.asyncio
async def test_process_stop_attendance_success(test_db_session: AsyncSession):
    employee = await _make_employee(test_db_session, "U_STOP_1", "stop1@example.com", "EMP_STOP_1")

    # An open session from a successful Start earlier today -- what Stop should close.
    open_log = AttendanceLog(
        employee_id=employee.id,
        date=datetime.now(),
        slack_event_id="evt_start_1",
        started=True,
        started_at=datetime.now(),
        status="success",
    )
    test_db_session.add(open_log)
    await test_db_session.commit()

    service = AttendanceService(test_db_session)

    mock_provider = AsyncMock()
    mock_provider.login.return_value = True
    mock_provider.stop_attendance.return_value = True

    with patch("app.services.attendance_service.get_attendance_provider", return_value=mock_provider):
        with patch("app.services.attendance_service.SlackClient.send_stop_success_reply", new_callable=AsyncMock) as mock_slack:
            await service.process_stop_attendance("U_STOP_1", "evt_stop_1", "D123")

            result = await test_db_session.execute(
                select(AttendanceLog).where(AttendanceLog.stop_slack_event_id == "evt_stop_1")
            )
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.id == open_log.id  # same row updated, not a new one
            assert log.ended is True
            assert log.ended_at is not None
            assert log.stop_status == "success"

            mock_slack.assert_called_once()


@pytest.mark.asyncio
async def test_process_stop_attendance_without_start_is_rejected(test_db_session: AsyncSession):
    employee = await _make_employee(test_db_session, "U_STOP_2", "stop2@example.com", "EMP_STOP_2")

    service = AttendanceService(test_db_session)

    with patch("app.services.attendance_service.SlackClient.send_not_started_reply", new_callable=AsyncMock) as mock_slack:
        await service.process_stop_attendance("U_STOP_2", "evt_stop_2", "D456")

        # No attendance_logs row should be touched or created for this employee today.
        result = await test_db_session.execute(
            select(AttendanceLog).where(AttendanceLog.employee_id == employee.id)
        )
        assert result.scalar_one_or_none() is None

        mock_slack.assert_called_once()


@pytest.mark.asyncio
async def test_process_stop_attendance_duplicate(test_db_session: AsyncSession):
    employee = await _make_employee(test_db_session, "U_STOP_3", "stop3@example.com", "EMP_STOP_3")

    already_stopped_log = AttendanceLog(
        employee_id=employee.id,
        date=datetime.now(),
        slack_event_id="evt_start_3",
        started=True,
        started_at=datetime.now(),
        status="success",
        ended=True,
        ended_at=datetime.now(),
        stop_slack_event_id="evt_stop_3_first",
        stop_status="success",
    )
    test_db_session.add(already_stopped_log)
    await test_db_session.commit()

    service = AttendanceService(test_db_session)

    with patch("app.services.attendance_service.SlackClient.send_stop_duplicate_reply", new_callable=AsyncMock) as mock_slack:
        await service.process_stop_attendance("U_STOP_3", "evt_stop_3_second", "D789")
        mock_slack.assert_called_once()
