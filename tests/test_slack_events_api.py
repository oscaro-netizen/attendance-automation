import hashlib
import hmac
import json
import time
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.session import get_db
from app.main import app
from app.models.models import AttendanceLog, Base, Employee
from app.slack.event_deduplicator import SlackEventDeduplicator, get_event_deduplicator
from app.utils.security import encrypt_password

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_slack_events.db"
ENDPOINT = "/api/v1/slack/events"


class FakeSlackEventDeduplicator(SlackEventDeduplicator):
    """
    In-memory stand-in for the Redis-backed deduplicator so tests do not
    require a live Redis instance. Implements the same public contract.
    """

    def __init__(self):  # intentionally skip the parent constructor (no Redis client)
        self._seen = set()

    async def is_duplicate(self, event_id: Optional[str]) -> bool:
        if not event_id:
            return False
        if event_id in self._seen:
            return True
        self._seen.add(event_id)
        return False


def _sign(body: bytes, timestamp: str, secret: str) -> str:
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _slack_headers(body: bytes, timestamp: Optional[str] = None, signature: Optional[str] = None) -> dict:
    ts = timestamp or str(int(time.time()))
    sig = signature if signature is not None else _sign(body, ts, settings.SLACK_SIGNING_SECRET)
    return {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
        "Content-Type": "application/json",
    }


def _start_report_event(event_id: str = "Ev001", user: str = "U100", channel: str = "C123") -> dict:
    return {
        "token": "verification-token",
        "team_id": "T123",
        "api_app_id": "A123",
        "event": {
            "type": "message",
            "channel": channel,
            "user": user,
            "text": "July 15, 2026 - Start\n\nTasks:\n\u2022 Task A\n\nExpected Today:\n\u2022 Goal A",
            "ts": "1626282600.000100",
        },
        "type": "event_callback",
        "event_id": event_id,
        "event_time": int(time.time()),
    }


@pytest.fixture(name="test_engine")
async def test_engine_fixture():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(name="test_db_session")
async def test_db_session_fixture(test_engine):
    async_session_maker = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session


@pytest.fixture(name="fake_deduplicator")
def fake_deduplicator_fixture():
    return FakeSlackEventDeduplicator()


@pytest.fixture(name="client")
async def client_fixture(test_engine, fake_deduplicator):
    async_session_maker = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with async_session_maker() as session:
            yield session

    async def override_get_event_deduplicator():
        return fake_deduplicator

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_event_deduplicator] = override_get_event_deduplicator

    client_instance = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    yield client_instance
    await client_instance.aclose()
    app.dependency_overrides.clear()


@pytest.fixture(name="registered_employee")
async def registered_employee_fixture(test_db_session: AsyncSession):
    employee = Employee(
        slack_user_id="U100",
        slack_username="alice",
        marsos_email="alice@example.com",
        marsos_employee_id="EMP100",
        marsos_password_encrypted=encrypt_password("secret"),
    )
    test_db_session.add(employee)
    await test_db_session.commit()
    await test_db_session.refresh(employee)
    return employee


# --------------------------------------------------------------------------
# URL verification
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_verification_challenge(client: AsyncClient):
    payload = {"token": "x", "challenge": "abc123", "type": "url_verification"}
    body = json.dumps(payload).encode()
    response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))
    assert response.status_code == 200
    assert response.json() == {"challenge": "abc123"}


# --------------------------------------------------------------------------
# Signature / replay protection
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_signature_rejected(client: AsyncClient):
    payload = _start_report_event()
    body = json.dumps(payload).encode()
    headers = _slack_headers(body, signature="v0=" + "0" * 64)
    response = await client.post(ENDPOINT, content=body, headers=headers)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_expired_timestamp_rejected(client: AsyncClient):
    payload = _start_report_event()
    body = json.dumps(payload).encode()
    old_ts = str(int(time.time()) - 3600)
    response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body, timestamp=old_ts))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_missing_signature_headers_rejected(client: AsyncClient):
    payload = _start_report_event()
    body = json.dumps(payload).encode()
    response = await client.post(ENDPOINT, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 401


# --------------------------------------------------------------------------
# Payload validation
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_json_rejected(client: AsyncClient):
    body = b"{not valid json"
    response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Event pipeline: unknown employee, duplicate, successful dispatch
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_employee_is_acknowledged_but_not_queued(client: AsyncClient, test_db_session):
    payload = _start_report_event(event_id="Ev-unknown", user="U999")
    body = json.dumps(payload).encode()

    with patch("app.slack.client.SlackClient.send_message", new_callable=AsyncMock) as mock_send:
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    assert response.json()["status"] == "employee_not_registered"
    mock_send.assert_called_once()


@pytest.mark.asyncio
async def test_successful_event_queues_celery_task(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-success", user="U100")
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="celery-task-abc")
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    body_json = response.json()
    assert body_json["status"] == "queued"
    mock_task.delay.assert_called_once_with("U100", "Ev-success", "C123")


@pytest.mark.asyncio
async def test_duplicate_event_is_not_queued_twice(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-dup", user="U100")
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="celery-task-1")

        first_response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))
        second_response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "queued"

    assert second_response.status_code == 200
    assert second_response.json()["status"] == "duplicate_event"

    mock_task.delay.assert_called_once()


@pytest.mark.asyncio
async def test_bot_message_is_ignored_and_not_queued(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-bot", user="U100")
    payload["event"]["bot_id"] = "B123"
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored_bot_event"
    mock_task.delay.assert_not_called()

@pytest.mark.asyncio
async def test_dm_stop_event_queues_stop_task(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-stop-dm", user="U100", channel="D999")
    payload["event"] = {
        "type": "message",
        "channel": "D999",
        "channel_type": "im",
        "user": "U100",
        "text": "July 16, 2026 - End",
        "ts": "1626282700.000100",
    }
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_stop_task") as mock_stop_task:
        mock_stop_task.delay.return_value = MagicMock(id="celery-stop-task-abc")
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    body_json = response.json()
    assert body_json["status"] == "queued_stop"
    mock_stop_task.delay.assert_called_once_with("U100", "Ev-stop-dm", "D999")

@pytest.mark.asyncio
async def test_stop_message_in_channel_not_dm_is_ignored(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-stop-channel", user="U100", channel="C123")
    payload["event"] = {
        "type": "message",
        "channel": "C123",
        "channel_type": "channel",
        "user": "U100",
        "text": "July 16, 2026 - End",
        "ts": "1626282800.000100",
    }
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_stop_task") as mock_stop_task:
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored_stop_not_dm"
    mock_stop_task.delay.assert_not_called()

@pytest.mark.asyncio
async def test_edited_message_is_ignored(client: AsyncClient, registered_employee):
    payload = _start_report_event(event_id="Ev-edit", user="U100")
    payload["event"]["subtype"] = "message_changed"
    body = json.dumps(payload).encode()

    with patch("app.services.slack_event_service.process_attendance_task") as mock_task:
        response = await client.post(ENDPOINT, content=body, headers=_slack_headers(body))

    assert response.status_code == 200
    assert response.json()["status"] == "ignored_message_subtype"
    mock_task.delay.assert_not_called()
