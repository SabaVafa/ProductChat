"""Shared API dependencies — admin authentication for write/admin endpoints."""

from fastapi import Header, HTTPException
from typing import Optional
from app.config import settings
import hmac
import logging

logger = logging.getLogger(__name__)


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> None:
    """Guard admin/write endpoints with a shared token (X-Admin-Token header).

    - ADMIN_TOKEN set  -> the header must match (constant-time compare), else 401.
    - ADMIN_TOKEN empty -> allowed in development (logged warning), denied (503)
      in any other environment, so it is never accidentally open in production.
    """
    expected = (settings.ADMIN_TOKEN or "").strip()

    if not expected:
        if settings.ENVIRONMENT == "development":
            logger.warning("ADMIN_TOKEN not set — admin endpoints are UNPROTECTED (development).")
            return
        raise HTTPException(status_code=503, detail="Admin disabled: ADMIN_TOKEN is not configured.")

    if not x_admin_token or not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token.")
