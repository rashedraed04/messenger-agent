"""
Dashboard authentication and session middleware.
"""

import logging
from typing import Any
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.db.client import get_supabase_anon_client

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "sb_access_token"


def get_current_user_optional(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any] | None:
    """
    Check if request has a valid Supabase Auth session token.
    Returns user dict or None.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        # In testing/development mode, if test session header is present
        if settings.app_env in ("development", "testing") and request.cookies.get("dev_user"):
            return {
                "id": "dev-user-001",
                "email": "owner@perfumestore.jo",
                "store_id": settings.default_store_id,
                "is_dev": True,
            }
        return None

    try:
        supabase = get_supabase_anon_client()
        user_resp = supabase.auth.get_user(token)
        if user_resp and user_resp.user:
            user_data = {
                "id": user_resp.user.id,
                "email": user_resp.user.email,
                # Address awaiting confirmation after an email change request
                "new_email": user_resp.user.new_email,
                "store_id": user_resp.user.app_metadata.get("store_id")
                or settings.default_store_id,
            }
            return user_data
    except Exception as e:
        logger.warning("Failed to validate Supabase auth token: %s", e)

    return None


def require_auth(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> dict[str, Any]:
    """
    FastAPI dependency: Enforce authenticated session on dashboard routes.
    Redirects to /auth/login if unauthenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/auth/login"},
        )
    return user
