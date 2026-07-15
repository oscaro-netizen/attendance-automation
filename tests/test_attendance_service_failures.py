import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.attendance_service import AttendanceService
from app.models.models import Employee, AttendanceLog
from app.schemas.schemas import AttendanceLogCreate
from app.utils.security import encrypt_password

@pytest.mark.asyncio
async def test_process_attendance_playwright_login_failure(test_db_session: AsyncSession):
    # Setup test employee
    password = "test_password"
    employee = Employee(
        slack_user_id="U_LOGIN_FAIL",
        slack_username="login_fail_user",
        marsos_email="login_fail@example.com",
        marsos_employee_id="EMP_LOGIN_FAIL",
        marsos_password_encrypted=encrypt_password(password)
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)

    service = AttendanceService(test_db_session)
    
    # Mock Playwright provider to fail login
    mock_provider = AsyncMock()
    mock_provider.login.return_value = False
    mock_provider.logout.return_value = None # Ensure logout is called even on failure
    
    with patch("app.services.attendance_service.get_attendance_provider", return_value=mock_provider):
        with patch("app.services.attendance_service.SlackClient.send_failure_reply", new_callable=AsyncMock) as mock_slack:
            await service.process_attendance("U_LOGIN_FAIL", "evt_login_fail", "C_LOGIN_FAIL")
            
            # Verify login was attempted
            mock_provider.login.assert_called_once_with(employee.marsos_email, password)
            
            # Verify database log
            from sqlalchemy import select
            result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.slack_event_id == "evt_login_fail"))
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.status == "failure"
            assert log.started is False
            assert log.failure_reason == "Automation failed"
            
            # Verify Slack reply
            mock_slack.assert_called_once()

@pytest.mark.asyncio
async def test_process_attendance_playwright_start_failure(test_db_session: AsyncSession):
    # Setup test employee
    password = "test_password"
    employee = Employee(
        slack_user_id="U_START_FAIL",
        slack_username="start_fail_user",
        marsos_email="start_fail@example.com",
        marsos_employee_id="EMP_START_FAIL",
        marsos_password_encrypted=encrypt_password(password)
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)

    service = AttendanceService(test_db_session)
    
    # Mock Playwright provider to fail start_attendance after successful login
    mock_provider = AsyncMock()
    mock_provider.login.return_value = True
    mock_provider.start_attendance.return_value = False
    mock_provider.logout.return_value = None
    
    with patch("app.services.attendance_service.get_attendance_provider", return_value=mock_provider):
        with patch("app.services.attendance_service.SlackClient.send_failure_reply", new_callable=AsyncMock) as mock_slack:
            await service.process_attendance("U_START_FAIL", "evt_start_fail", "C_START_FAIL")
            
            # Verify login and start_attendance were attempted
            mock_provider.login.assert_called_once_with(employee.marsos_email, password)
            mock_provider.start_attendance.assert_called_once_with(employee.marsos_employee_id)
            
            # Verify database log
            from sqlalchemy import select
            result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.slack_event_id == "evt_start_fail"))
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.status == "failure"
            assert log.started is False
            assert log.failure_reason == "Automation failed"
            
            # Verify Slack reply
            mock_slack.assert_called_once()

@pytest.mark.asyncio
async def test_process_attendance_missing_credentials(test_db_session: AsyncSession):
    # Setup test employee without encrypted password
    employee = Employee(
        slack_user_id="U_NO_PASS",
        slack_username="no_pass_user",
        marsos_email="no_pass@example.com",
        marsos_employee_id="EMP_NO_PASS",
        marsos_password_encrypted=None
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)

    service = AttendanceService(test_db_session)
    
    # Mock Playwright provider to ensure it's not called
    mock_provider = AsyncMock()
    
    with patch("app.services.attendance_service.get_attendance_provider", return_value=mock_provider):
        with patch("app.services.attendance_service.SlackClient.send_failure_reply", new_callable=AsyncMock) as mock_slack:
            await service.process_attendance("U_NO_PASS", "evt_no_pass", "C_NO_PASS")
            
            # Verify Playwright login was NOT attempted
            mock_provider.login.assert_not_called()
            
            # Verify database log
            from sqlalchemy import select
            result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.slack_event_id == "evt_no_pass"))
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.status == "failure"
            assert log.started is False
            assert log.failure_reason == "Missing credentials"
            
            # Verify Slack reply
            mock_slack.assert_called_once()
