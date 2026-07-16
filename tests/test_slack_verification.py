import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import settings
from app.middleware.slack_verification import verify_slack_signature


def _sign(body: bytes, timestamp: str, secret: str) -> str:
    basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    digest = hmac.new(secret.encode("utf-8"), basestring.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _make_request(body: bytes, headers: dict) -> Request:
    """Builds a minimal ASGI Request with a pre-set body, bypassing the network."""
    encoded_headers = [
        (k.lower().encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()
    ]
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/slack/events",
        "headers": encoded_headers,
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


@pytest.mark.asyncio
async def test_valid_signature_passes():
    body = b'{"type": "url_verification", "challenge": "abc"}'
    timestamp = str(int(time.time()))
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": _sign(body, timestamp, settings.SLACK_SIGNING_SECRET),
    }
    request = _make_request(body, headers)
    # Should not raise
    await verify_slack_signature(request)


@pytest.mark.asyncio
async def test_missing_headers_rejected():
    body = b'{"type": "url_verification", "challenge": "abc"}'
    request = _make_request(body, {})
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_signature(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_invalid_signature_rejected():
    body = b'{"type": "url_verification", "challenge": "abc"}'
    timestamp = str(int(time.time()))
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": "v0=" + "0" * 64,
    }
    request = _make_request(body, headers)
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_signature(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_expired_timestamp_rejected():
    body = b'{"type": "url_verification", "challenge": "abc"}'
    old_timestamp = str(int(time.time()) - 3600)
    headers = {
        "X-Slack-Request-Timestamp": old_timestamp,
        "X-Slack-Signature": _sign(body, old_timestamp, settings.SLACK_SIGNING_SECRET),
    }
    request = _make_request(body, headers)
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_signature(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_non_numeric_timestamp_rejected():
    body = b'{"type": "url_verification", "challenge": "abc"}'
    headers = {
        "X-Slack-Request-Timestamp": "not-a-number",
        "X-Slack-Signature": "v0=" + "0" * 64,
    }
    request = _make_request(body, headers)
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_signature(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_tampered_body_rejected():
    original_body = b'{"type": "url_verification", "challenge": "abc"}'
    timestamp = str(int(time.time()))
    headers = {
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": _sign(original_body, timestamp, settings.SLACK_SIGNING_SECRET),
    }
    tampered_body = b'{"type": "url_verification", "challenge": "hijacked"}'
    request = _make_request(tampered_body, headers)
    with pytest.raises(HTTPException) as exc_info:
        await verify_slack_signature(request)
    assert exc_info.value.status_code == 401
