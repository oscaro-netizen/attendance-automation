"""
Verification of inbound Slack webhooks.

The webhook URL is public, so the request has to prove its own origin. Slack
signs each request with a shared secret; we recompute the signature and compare.

Reference: https://api.slack.com/authentication/verifying-requests-from-slack
"""
import hashlib
import hmac
import logging
import time

from fastapi import HTTPException, Request, status

from app.config import settings

logger = logging.getLogger(__name__)

SIGNATURE_VERSION = "v0"

# One opaque message for every rejection path. Telling a caller *which* check
# failed only helps someone probing the endpoint.
_REJECTION_DETAIL = "Invalid Slack signature"


def _reject(reason: str) -> HTTPException:
    logger.warning("Rejecting Slack request: %s", reason)
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REJECTION_DETAIL)


async def verify_slack_signature(request: Request) -> None:
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        raise _reject("missing signature or timestamp header")

    # A non-numeric timestamp is a malformed request, not a server error.
    try:
        timestamp_seconds = int(timestamp)
    except ValueError:
        raise _reject("non-numeric X-Slack-Request-Timestamp header")

    if abs(time.time() - timestamp_seconds) > settings.SLACK_TIMESTAMP_TOLERANCE_SECONDS:
        raise _reject("timestamp outside the accepted tolerance window")

    if not signature.startswith(f"{SIGNATURE_VERSION}="):
        raise _reject(f"unexpected signature version (expected {SIGNATURE_VERSION}=)")

    # The signature covers the exact bytes Slack sent. Re-serialising the parsed
    # JSON would produce different bytes and therefore a false mismatch.
    body = await request.body()
    basestring = SIGNATURE_VERSION.encode() + b":" + timestamp.encode() + b":" + body

    expected = f"{SIGNATURE_VERSION}=" + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode(),
        basestring,
        hashlib.sha256,
    ).hexdigest()

    # Constant-time comparison: a plain `==` returns faster the earlier it finds
    # a difference, which leaks the correct signature one character at a time.
    if not hmac.compare_digest(expected, signature):
        raise _reject("signature mismatch")
