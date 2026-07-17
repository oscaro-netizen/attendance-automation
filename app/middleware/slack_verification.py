import hmac
import hashlib
import time
from fastapi import Request, HTTPException
from app.core.config import settings
from loguru import logger

async def verify_slack_signature(request: Request):
    """
    Verifies the signature of incoming Slack requests using raw bytes.
    """
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    if not timestamp or not signature:
        logger.warning("Missing Slack signature or timestamp")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    # Prevent replay attacks
    if abs(time.time() - int(timestamp)) > settings.SLACK_REQUEST_TIMESTAMP_TOLERANCE_SECONDS:
        logger.warning("Slack request timestamp too old")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    # IMPORTANT: Get raw bytes directly
    body = await request.body()
    
    # Construct the base string using bytes to avoid encoding issues
    sig_basestring = b"v0:" + timestamp.encode('utf-8') + b":" + body
    
    # Calculate signature
    computed_signature = 'v0=' + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode('utf-8'),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, signature):
        # Debugging tip: Log the first 5 chars of the secret to ensure it's loaded
        logger.warning(f"Signature mismatch. Secret starts with: {settings.SLACK_SIGNING_SECRET[:3]}...")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    return True
