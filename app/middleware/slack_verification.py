import hashlib
import hmac
import time

from fastapi import HTTPException, Request, status
from loguru import logger

from app.core.config import settings

# Slack's current signature version prefix.
SIGNATURE_VERSION = "v0"

# A single opaque message for every rejection path: distinguishing "missing
# header" from "bad signature" from "stale timestamp" only helps an attacker
# probe the endpoint.
_REJECTION_DETAIL = "Invalid Slack signature"


def _reject(reason: str) -> HTTPException:
    logger.warning(f"Rejecting Slack request: {reason}")
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_REJECTION_DETAIL)


async def verify_slack_signature(request: Request):
    """
    Verifies the signature of incoming Slack requests using raw bytes.

    Reference: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        raise _reject("missing signature or timestamp header")

    # A non-numeric timestamp is a malformed request, not a server error; parse
    # defensively so it produces 401 rather than an uncaught ValueError -> 500.
    try:
        timestamp_seconds = int(timestamp)
    except ValueError:
        raise _reject("non-numeric X-Slack-Request-Timestamp header")

    # Prevent replay attacks
    if abs(time.time() - timestamp_seconds) > settings.SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS:
        raise _reject("timestamp outside the accepted tolerance window")

    if not signature.startswith(f"{SIGNATURE_VERSION}="):
        raise _reject(f"unexpected signature version (expected {SIGNATURE_VERSION}=)")

    # IMPORTANT: Get raw bytes directly. Re-serializing the parsed JSON would
    # produce different bytes than Slack signed.
    body = await request.body()

    # Construct the base string using bytes to avoid encoding issues
    sig_basestring = SIGNATURE_VERSION.encode() + b":" + timestamp.encode("utf-8") + b":" + body

    computed_signature = f"{SIGNATURE_VERSION}=" + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode("utf-8"),
        sig_basestring,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed_signature, signature):
        raise _reject("signature mismatch")

    return True
