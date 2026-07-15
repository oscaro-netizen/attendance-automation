import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.config import settings
from app.database.session import get_db
from app.models.models import Base, Employee, AttendanceLog
from datetime import datetime, date

from sqlalchemy import select

# Use a test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest.fixture(name="test_engine")
async def test_engine_fixture():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(name="test_db_session")
async def test_db_session_fixture(test_engine):
    async_session_maker = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session

@pytest.fixture(name="client")
async def client_fixture(test_engine):
    async_session_maker = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async def override_get_db():
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client_instance = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client_instance
    await client_instance.aclose() # Ensure the client is properly closed
    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_create_employee(client: AsyncClient, test_db_session: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567890",
        "slack_username": "testuser",
        "marsos_email": "test@example.com",
        "marsos_employee_id": "EMP001",
        "marsos_password": "secure_password"
    }
    response = await client.post("/api/v1/employees", json=employee_data)
    assert response.status_code == 200
    assert response.json()["slack_user_id"] == "U1234567890"
    # Password should NOT be in the response
    assert "marsos_password" not in response.json()
    assert "marsos_password_encrypted" not in response.json()

    # Verify in DB
    result = await test_db_session.execute(select(Employee).where(Employee.slack_user_id == "U1234567890"))
    employee = result.scalar_one_or_none()
    assert employee is not None
    assert employee.marsos_password_encrypted is not None

@pytest.mark.asyncio
async def test_get_employees(client: AsyncClient, test_db_session: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567891",
        "slack_username": "testuser2",
        "marsos_email": "test2@example.com",
        "marsos_employee_id": "EMP002",
        "marsos_password": "password"
    }
    await client.post("/api/v1/employees", json=employee_data)

    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert any(e["slack_user_id"] == "U1234567891" for e in response.json())

@pytest.mark.asyncio
async def test_create_attendance_log(client: AsyncClient, test_db_session: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567892",
        "slack_username": "testuser3",
        "marsos_email": "test3@example.com",
        "marsos_employee_id": "EMP003",
        "marsos_password": "password"
    }
    emp_response = await client.post("/api/v1/employees", json=employee_data)
    employee_id = emp_response.json()["id"]

    log_data = {
        "employee_id": employee_id,
        "date": datetime.now().isoformat(),
        "started": True,
        "status": "success",
        "started_at": datetime.now().isoformat()
    }
    response = await client.post("/api/v1/attendance", json=log_data)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Verify in DB
    result = await test_db_session.execute(select(AttendanceLog).where(AttendanceLog.employee_id == employee_id))
    log = result.scalar_one_or_none()
    assert log is not None

@pytest.mark.asyncio
async def test_get_attendance_logs(client: AsyncClient, test_db_session: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567893",
        "slack_username": "testuser4",
        "marsos_email": "test4@example.com",
        "marsos_employee_id": "EMP004",
        "marsos_password": "password"
    }
    emp_response = await client.post("/api/v1/employees", json=employee_data)
    employee_id = emp_response.json()["id"]

    log_data = {
        "employee_id": employee_id,
        "date": datetime.now().isoformat(),
        "started": True,
        "status": "success",
        "started_at": datetime.now().isoformat()
    }
    await client.post("/api/v1/attendance", json=log_data)

    response = await client.get("/api/v1/attendance")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert any(l["employee_id"] == employee_id for l in response.json())
