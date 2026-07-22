import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.middleware.slack_verification import verify_slack_signature
from tests.conftest import TEST_SIGNING_SECRET

pytestmark = pytest.mark.asyncio


class StubRequest:
    def __init__(self, headers: dict, body: bytes):
        self.headers = headers
        self._body = body

    async def body(self) -> bytes:
        return self._body


def sign(body: bytes, timestamp: str, secret: str = TEST_SIGNING_SECRET) -> str:
    basestring = b"v0:" + timestamp.encode() + b":" + body
    return "v0=" + hmac.new(secret.encode(), basestring, hashlib.sha256).hexdigest()


def make_request(body: bytes = b'{"type":"url_verification"}', timestamp: str = None, signature: str = None):
    timestamp = timestamp if timestamp is not None else str(int(time.time()))
    signature = signature if signature is not None else sign(body, timestamp)
    return StubRequest(
        headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature},
        body=body,
    )


async def test_accepts_a_correctly_signed_request():
    assert await verify_slack_signature(make_request()) is True


async def test_signature_is_computed_over_the_exact_raw_body():
    body = b'{"type":"event_callback","event":{"text":"caf\\u00e9"}}'
    assert await verify_slack_signature(make_request(body=body)) is True


async def test_rejects_a_signature_made_with_the_wrong_secret():
    body = b'{"a":1}'
    timestamp = str(int(time.time()))
    request = make_request(body=body, timestamp=timestamp, signature=sign(body, timestamp, "wrong_secret"))
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(request)
    assert exc.value.status_code == 401


async def test_rejects_a_body_tampered_with_after_signing():
    timestamp = str(int(time.time()))
    signature = sign(b'{"amount":1}', timestamp)
    request = make_request(body=b'{"amount":9999}', timestamp=timestamp, signature=signature)
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(request)
    assert exc.value.status_code == 401


async def test_rejects_a_replayed_request_outside_the_tolerance_window():
    stale = str(int(time.time()) - settings.SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS - 60)
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(make_request(timestamp=stale))
    assert exc.value.status_code == 401


async def test_rejects_a_timestamp_from_the_far_future():
    future = str(int(time.time()) + settings.SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS + 60)
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(make_request(timestamp=future))
    assert exc.value.status_code == 401


async def test_a_non_numeric_timestamp_is_a_401_not_a_500():
    """Regression: `int(timestamp)` used to raise ValueError straight out of the dependency."""
    request = StubRequest(
        headers={"X-Slack-Request-Timestamp": "not-a-number", "X-Slack-Signature": "v0=abc"},
        body=b"{}",
    )
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(request)
    assert exc.value.status_code == 401


async def test_rejects_an_unexpected_signature_version():
    body = b"{}"
    timestamp = str(int(time.time()))
    request = make_request(body=body, timestamp=timestamp, signature="v1=" + sign(body, timestamp)[3:])
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(request)
    assert exc.value.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Slack-Request-Timestamp": "1720000000"},
        {"X-Slack-Signature": "v0=deadbeef"},
    ],
)
async def test_rejects_requests_missing_either_header(headers):
    with pytest.raises(HTTPException) as exc:
        await verify_slack_signature(StubRequest(headers=headers, body=b"{}"))
    assert exc.value.status_code == 401


async def test_rejection_detail_does_not_reveal_which_check_failed():
    """All rejection paths return the same opaque message."""
    details = set()
    for request in (
        StubRequest(headers={}, body=b"{}"),
        make_request(timestamp="0"),
        make_request(signature="v0=deadbeef"),
    ):
        with pytest.raises(HTTPException) as exc:
            await verify_slack_signature(request)
        details.add(exc.value.detail)
    assert len(details) == 1
