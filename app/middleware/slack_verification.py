import hmac
import hashlib
import time
from fastapi import Request, HTTPException
from app.core.config import settings
from loguru import logger

SLACK_SIGNATURE_VERSION = "v0"


async def verify_slack_signature(request: Request) -> None:
    """
    FastAPI dependency that verifies a request genuinely originated from
    Slack, per https://api.slack.com/authentication/verifying-requests-from-slack

    Enforced, in order:
      1. Both required headers are present.
      2. The timestamp header is well-formed and within the configured
         tolerance window of server time (replay-attack protection).
      3. The HMAC-SHA256 signature, computed over the exact raw request
         body, matches -- compared using a constant-time comparison
         (timing-attack protection).

    Raises HTTPException(401) on any failure. Never raises an unhandled
    exception on malformed input.
    """
    timestamp_header = request.headers.get("X-Slack-Request-Timestamp")
    signature_header = request.headers.get("X-Slack-Signature")

    if not timestamp_header or not signature_header:
        logger.warning("Rejected Slack request: missing signature headers")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    try:
        timestamp = int(timestamp_header)
    except ValueError:
        logger.warning("Rejected Slack request: non-numeric X-Slack-Request-Timestamp")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    tolerance_seconds = settings.SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS
    if abs(time.time() - timestamp) > tolerance_seconds:
        logger.warning("Rejected Slack request: timestamp outside tolerance window (possible replay attack)")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    body = await request.body()
    try:
        decoded_body = body.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("Rejected Slack request: body is not valid UTF-8")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    sig_basestring = f"{SLACK_SIGNATURE_VERSION}:{timestamp_header}:{decoded_body}"

    computed_signature = (
        f"{SLACK_SIGNATURE_VERSION}="
        + hmac.new(
            settings.SLACK_SIGNING_SECRET.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )

    # hmac.compare_digest is constant-time and protects against
    # timing side-channel attacks on the signature comparison.
    if not hmac.compare_digest(computed_signature, signature_header):
        logger.warning("Rejected Slack request: signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
