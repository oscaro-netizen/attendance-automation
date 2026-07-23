"""Shared FastAPI dependencies."""
import hmac
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from loguru import logger

from app.core.config import settings

ADMIN_API_KEY_HEADER = "X-Admin-API-Key"
api_key_header = APIKeyHeader(name=ADMIN_API_KEY_HEADER, auto_error=False)


async def require_admin(x_admin_api_key: Optional[str] = Depends(api_key_header)) -> None:
    """
    Guards the employee and attendance management endpoints.

    These routes expose employee records and accept plaintext MarsOS passwords,
    so they must not be reachable by anyone who can hit the service. Unlike the
    Slack webhook -- which authenticates via signature -- they have no inherent
    caller identity, hence a shared admin key.

    Fails closed: if `ADMIN_API_KEY` is unset the endpoints are unavailable
    rather than unauthenticated.
    """
    if not settings.ADMIN_API_KEY:
        logger.error("ADMIN_API_KEY is not configured; admin endpoints are disabled")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is not configured. Please set ADMIN_API_KEY in your .env file.",
        )

    if not x_admin_api_key or not hmac.compare_digest(x_admin_api_key, settings.ADMIN_API_KEY):
        logger.warning("Rejected admin request with missing or invalid API key")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Missing or invalid {ADMIN_API_KEY_HEADER} header",
        )
