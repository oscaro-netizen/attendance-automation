"""The webhook is public, so signature verification is the only thing keeping it honest."""
import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import TEST_SIGNING_SECRET

WEBHOOK = "/slack/events"


def sign(body: bytes, timestamp: str, secret: str = TEST_SIGNING_SECRET) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def headers_for(body: bytes, timestamp: str | None = None, secret: str = TEST_SIGNING_SECRET) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    return {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": sign(body, timestamp, secret),
        "Content-Type": "application/json",
    }


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_a_correctly_signed_request_is_accepted(client):
    body = b'{"type":"url_verification","challenge":"abc"}'
    response = client.post(WEBHOOK, content=body, headers=headers_for(body))
    assert response.status_code == 200
    assert response.json() == {"challenge": "abc"}


def test_missing_headers_are_rejected(client):
    assert client.post(WEBHOOK, content=b"{}").status_code == 401


def test_a_wrong_signature_is_rejected(client):
    body = b'{"type":"url_verification","challenge":"abc"}'
    response = client.post(WEBHOOK, content=body, headers=headers_for(body, secret="not_the_secret"))
    assert response.status_code == 401


def test_a_tampered_body_is_rejected(client):
    """The signature covers the body, so altering it after signing must fail."""
    body = b'{"type":"url_verification","challenge":"abc"}'
    sent_headers = headers_for(body)
    response = client.post(WEBHOOK, content=b'{"type":"url_verification","challenge":"XYZ"}', headers=sent_headers)
    assert response.status_code == 401


def test_an_old_timestamp_is_rejected_as_a_replay(client):
    body = b"{}"
    stale = str(int(time.time()) - 10_000)
    assert client.post(WEBHOOK, content=body, headers=headers_for(body, timestamp=stale)).status_code == 401


def test_a_non_numeric_timestamp_is_rejected_not_crashed(client):
    """A malformed header must be a 401, not an unhandled ValueError -> 500."""
    body = b"{}"
    response = client.post(
        WEBHOOK,
        content=body,
        headers={"X-Slack-Request-Timestamp": "not-a-number", "X-Slack-Signature": "v0=deadbeef"},
    )
    assert response.status_code == 401


def test_an_unexpected_signature_version_is_rejected(client):
    body = b"{}"
    response = client.post(
        WEBHOOK,
        content=body,
        headers={"X-Slack-Request-Timestamp": str(int(time.time())), "X-Slack-Signature": "v9=deadbeef"},
    )
    assert response.status_code == 401


def test_every_rejection_gives_the_same_message(client):
    """Distinguishing failure modes only helps someone probing the endpoint."""
    body = b"{}"
    missing = client.post(WEBHOOK, content=body)
    wrong = client.post(WEBHOOK, content=body, headers=headers_for(body, secret="wrong"))
    assert missing.json()["detail"] == wrong.json()["detail"]
