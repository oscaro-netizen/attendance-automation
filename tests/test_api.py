import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.config import settings
from app.database.session import get_db
from app.models.models import Base, Employee, AttendanceLog
from datetime import datetime, date

# Use a test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

@pytest.fixture(name="test_db")
async def test_db_fixture():
    engine = create_async_engine(TEST_DATABASE_URL, echo=True)
    async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with async_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    yield async_session_maker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture(name="client")
async def client_fixture(test_db: AsyncSession):
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@pytest.mark.asyncio
async def test_create_employee(client: AsyncClient, test_db: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567890",
        "slack_username": "testuser",
        "marsos_email": "test@example.com",
        "marsos_employee_id": "EMP001"
    }
    response = await client.post("/api/v1/employees", json=employee_data)
    assert response.status_code == 200
    assert response.json()["slack_user_id"] == "U1234567890"

    # Verify in DB
    async with test_db() as session:
        employee = await session.execute(select(Employee).where(Employee.slack_user_id == "U1234567890"))
        assert employee.scalar_one_or_none() is not None

@pytest.mark.asyncio
async def test_get_employees(client: AsyncClient, test_db: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567891",
        "slack_username": "testuser2",
        "marsos_email": "test2@example.com",
        "marsos_employee_id": "EMP002"
    }
    await client.post("/api/v1/employees", json=employee_data)

    response = await client.get("/api/v1/employees")
    assert response.status_code == 200
    assert len(response.json()) > 0
    assert response.json()[0]["slack_user_id"] == "U1234567891"

@pytest.mark.asyncio
async def test_create_attendance_log(client: AsyncClient, test_db: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567892",
        "slack_username": "testuser3",
        "marsos_email": "test3@example.com",
        "marsos_employee_id": "EMP003"
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
    async with test_db() as session:
        log = await session.execute(select(AttendanceLog).where(AttendanceLog.employee_id == employee_id))
        assert log.scalar_one_or_none() is not None

@pytest.mark.asyncio
async def test_get_attendance_logs(client: AsyncClient, test_db: AsyncSession):
    employee_data = {
        "slack_user_id": "U1234567893",
        "slack_username": "testuser4",
        "marsos_email": "test4@example.com",
        "marsos_employee_id": "EMP004"
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
    assert response.json()[0]["employee_id"] == employee_id
