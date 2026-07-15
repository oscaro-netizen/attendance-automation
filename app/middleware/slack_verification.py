import hmac
import hashlib
import time
from fastapi import Request, HTTPException
from app.core.config import settings
from loguru import logger

async def verify_slack_signature(request: Request):
    """
    Verifies the signature of incoming Slack requests.
    """
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    
    if not timestamp or not signature:
        logger.warning("Missing Slack signature or timestamp")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    # Prevent replay attacks
    if abs(time.time() - int(timestamp)) > 60 * 5:
        logger.warning("Slack request timestamp too old")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    body = await request.body()
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    
    computed_signature = 'v0=' + hmac.new(
        settings.SLACK_SIGNING_SECRET.encode('utf-8'),
        sig_basestring.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, signature):
        logger.warning("Slack signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")
        
    return True
