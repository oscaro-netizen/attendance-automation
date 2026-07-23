"""End-to-end webhook behaviour: what gets acted on, what gets ignored."""
import json

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.messages import Action
from app.store import put_token
from tests.test_slack_verify import WEBHOOK, headers_for

START_REPORT = "July 23, 2026 - Start\n\nTasks:\n• a\n\nExpected Today:\n• b"
USER = "U04TQ9XKMLR"


@pytest.fixture
def actions(monkeypatch):
    """Captures what would have been sent to TimeTrack, without calling it."""
    captured = []

    async def fake_run_action(slack_user_id, action, token):
        captured.append((slack_user_id, action, token))

    monkeypatch.setattr(main, "run_action", fake_run_action)
    return captured


@pytest.fixture
def client(db_path):
    with TestClient(main.app) as test_client:
        yield test_client


def post(client, event: dict, envelope_type: str = "event_callback"):
    body = json.dumps({"type": envelope_type, "event_id": "Ev123", "event": event}).encode()
    return client.post(WEBHOOK, content=body, headers=headers_for(body))


def message(**overrides) -> dict:
    event = {"type": "message", "user": USER, "channel": "C_TEST", "text": START_REPORT}
    event.update(overrides)
    return event


def test_a_start_report_from_a_registered_employee_is_accepted(client, actions):
    put_token(USER, "tok-123")
    response = post(client, message())
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert actions == [(USER, Action.CLOCK_IN, "tok-123")]


def test_a_completed_work_report_clocks_out(client, actions):
    put_token(USER, "tok-123")
    post(client, message(text="July 23, 2026 - End\n\nCompleted Work:\n• invoice export merged"))
    assert actions == [(USER, Action.CLOCK_OUT, "tok-123")]


def test_an_unregistered_user_queues_nothing(client, actions):
    response = post(client, message())
    assert response.status_code == 200
    assert response.json()["status"] == "unregistered"
    assert actions == []


def test_the_url_verification_handshake_is_answered(client):
    body = json.dumps({"type": "url_verification", "challenge": "c-123"}).encode()
    response = client.post(WEBHOOK, content=body, headers=headers_for(body))
    assert response.json() == {"challenge": "c-123"}


def test_malformed_json_is_a_400_not_a_crash(client):
    body = b"{not json"
    assert client.post(WEBHOOK, content=body, headers=headers_for(body)).status_code == 400


@pytest.mark.parametrize(
    "event",
    [
        message(bot_id="B123"),
        message(subtype="bot_message"),
        message(subtype="message_changed"),
        message(subtype="message_deleted"),
        message(thread_ts="1234.5678"),
        message(type="reaction_added"),
        message(channel="C_SOMEWHERE_ELSE"),
        message(text="just chatting"),
        message(user=None),
    ],
)
def test_events_that_must_never_trigger_anything(client, actions, event):
    put_token(USER, "tok-123")
    response = post(client, event)
    assert response.status_code == 200
    assert actions == []


def test_a_non_event_callback_envelope_is_ignored(client, actions):
    put_token(USER, "tok-123")
    response = post(client, message(), envelope_type="something_else")
    assert response.status_code == 200
    assert actions == []


def test_health_is_open(client):
    assert client.get("/health").status_code == 200


def test_api_docs_are_not_served(client):
    """The schema lists every route and payload shape; nothing in production needs it."""
    for url in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(url).status_code == 404
