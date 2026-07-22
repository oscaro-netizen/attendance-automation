"""HTTP-level behaviour of the Slack webhook."""
import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.middleware.slack_verification import verify_slack_signature
from app.services import slack_event_service as ses
from app.slack.event_deduplicator import get_event_deduplicator
from tests.conftest import TEST_SIGNING_SECRET
from tests.factories import FakeDeduplicator, FakeTask, message_event

EVENTS_URL = "/api/v1/events"


def signed_headers(body: bytes) -> dict:
    timestamp = str(int(time.time()))
    basestring = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(TEST_SIGNING_SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
        "Content-Type": "application/json",
    }


def post(client: TestClient, payload) -> "object":
    body = json.dumps(payload).encode()
    return client.post(EVENTS_URL, content=body, headers=signed_headers(body))


@pytest.fixture
def client(db_session, monkeypatch):
    """A TestClient with the database and deduplicator dependencies overridden."""
    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_event_deduplicator] = lambda: FakeDeduplicator()
    monkeypatch.setattr(ses, "process_attendance_task", FakeTask("task-start"))
    monkeypatch.setattr(ses, "process_logout_task", FakeTask("task-end"))
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


class TestAuthentication:
    def test_an_unsigned_request_is_rejected(self, client):
        response = client.post(EVENTS_URL, json=message_event())
        assert response.status_code == 401

    def test_a_request_with_a_forged_signature_is_rejected(self, client):
        body = json.dumps(message_event()).encode()
        headers = signed_headers(body)
        headers["X-Slack-Signature"] = "v0=" + "0" * 64
        assert client.post(EVENTS_URL, content=body, headers=headers).status_code == 401


class TestHandshake:
    def test_the_url_verification_challenge_is_echoed_back(self, client):
        response = post(client, {"type": "url_verification", "challenge": "abc123"})
        assert response.status_code == 200
        assert response.json() == {"challenge": "abc123"}


class TestPayloadHandling:
    def test_a_valid_start_report_is_accepted_and_queued(self, client, employee):
        response = post(client, message_event())
        assert response.status_code == 200
        assert response.json()["status"] == "queued_start"

    def test_the_end_command_is_accepted_and_queued(self, client, employee):
        response = post(client, message_event(text="\\end"))
        assert response.status_code == 200
        assert response.json()["status"] == "queued_end"

    def test_an_ignored_event_still_returns_200(self, client, employee):
        """Anything other than 2xx makes Slack redeliver the event."""
        response = post(client, message_event(text="just chatting"))
        assert response.status_code == 200
        assert response.json()["status"] == "ignored_invalid_format"

    def test_a_malformed_payload_is_rejected_with_400(self, client):
        response = post(client, {"no_type_field": True})
        assert response.status_code == 400

    def test_invalid_json_is_rejected_with_400(self, client):
        body = b"{not json"
        response = client.post(EVENTS_URL, content=body, headers=signed_headers(body))
        assert response.status_code == 400

    def test_every_response_carries_a_request_id_for_tracing(self, client, employee):
        assert post(client, message_event()).json()["request_id"]


class TestBrokerFailure:
    def test_a_broker_failure_returns_503_so_slack_retries(self, client, employee, monkeypatch):
        monkeypatch.setattr(ses, "process_attendance_task", FakeTask(raises=True))
        response = post(client, message_event())
        assert response.status_code == 503
