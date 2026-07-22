"""
Shared test fixtures.

Settings are populated from environment defaults *before* `app.*` is imported,
so importing the app under test never depends on a developer's local `.env`.
The database is an in-memory SQLite instance created fresh per test, which keeps
the suite hermetic and fast; no Postgres, Redis, Slack, or browser is required.
"""
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# --- Test environment ---------------------------------------------------------
# Must be set before `app.core.config` is imported anywhere.
TEST_SIGNING_SECRET = "test_signing_secret"
TEST_ADMIN_API_KEY = "test_admin_api_key"

os.environ.setdefault("SLACK_SIGNING_SECRET", TEST_SIGNING_SECRET)
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_CHANNEL_ID", "C_TEST_CHANNEL")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("MARSOS_BASE_URL", "https://marsos.test")
os.environ.setdefault("ADMIN_API_KEY", TEST_ADMIN_API_KEY)
os.environ.setdefault("ATTENDANCE_TIMEZONE", "UTC")

from cryptography.fernet import Fernet  # noqa: E402

os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())

from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.models import Base, Employee  # noqa: E402
from app.utils.security import encrypt_password  # noqa: E402


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """A fresh in-memory database per test, with the schema created."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def employee(db_session: AsyncSession) -> Employee:
    """A registered employee with a decryptable MarsOS password."""
    emp = Employee(
        slack_user_id="U_TEST_123",
        slack_username="test_user",
        marsos_email="test@example.com",
        marsos_employee_id="EMP_TEST_001",
        marsos_password_encrypted=encrypt_password("test_password"),
    )
    db_session.add(emp)
    await db_session.commit()
    await db_session.refresh(emp)
    return emp
