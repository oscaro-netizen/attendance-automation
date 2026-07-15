import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.attendance_service import AttendanceService
from app.models.models import Employee, AttendanceLog
from app.schemas.schemas import EmployeeCreate
from app.utils.security import encrypt_password

@pytest.mark.asyncio
async def test_process_attendance_success(test_db_session: AsyncSession):
    # Setup test employee
    password = "test_password"
    employee = Employee(
        slack_user_id="U123",
        slack_username="testuser",
        marsos_email="test@example.com",
        marsos_employee_id="EMP001",
        marsos_password_encrypted=encrypt_password(password)
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)

    service = AttendanceService(test_db_session)
    
    # Mock Playwright provider
    mock_provider = AsyncMock()
    mock_provider.login.return_value = True
    mock_provider.start_attendance.return_value = True
    
    with patch("app.services.attendance_service.get_attendance_provider", return_value=mock_provider):
        with patch("app.services.attendance_service.SlackClient.send_success_reply", new_callable=AsyncMock) as mock_slack:
            await service.process_attendance("U123", "evt_123", "C123")
            
            # Verify database log
            from sqlalchemy import select
            result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.slack_event_id == "evt_123"))
            log = result.scalar_one_or_none()
            assert log is not None
            assert log.status == "success"
            assert log.started is True
            
            # Verify Slack reply
            mock_slack.assert_called_once()

@pytest.mark.asyncio
async def test_process_attendance_duplicate(test_db_session: AsyncSession):
    # Setup test employee and existing log
    employee = Employee(
        slack_user_id="U456",
        slack_username="testuser2",
        marsos_email="test2@example.com",
        marsos_employee_id="EMP002"
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)
    
    # Existing log for today
    existing_log = AttendanceLog(
        employee_id=employee.id,
        date=datetime.now(),
        status="success",
        started=True
    )
    test_db_session.add(existing_log)
    await test_db_session.commit()

    service = AttendanceService(test_db_session)
    
    with patch("app.services.attendance_service.SlackClient.send_duplicate_reply", new_callable=AsyncMock) as mock_slack:
        await service.process_attendance("U456", "evt_456", "C456")
        
        # Verify Slack reply
        mock_slack.assert_called_once()
        
        # Verify new log entry for duplicate
        from sqlalchemy import select
        result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.slack_event_id == "evt_456"))
        log = result.scalar_one_or_none()
        assert log is not None
        assert log.status == "duplicate"
