"""
Dashboard authentication and session middleware.
"""

import logging
from typing import Any

from fastapi import Depends, HTTPException, Request, status

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
                "email": "owner@example.com",
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
                # Set in Supabase (app_metadata.role = "demo"); users can't edit app_metadata
                "is_demo": user_resp.user.app_metadata.get("role") == "demo",
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
    request.state.is_demo = bool(user.get("is_demo"))
    return user


# The demo account may chat with the bot simulator but change nothing else
DEMO_ALLOWED_WRITES = {"/dashboard/chat/send", "/dashboard/chat/reset"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def block_demo_writes(
    request: Request,
    user: dict[str, Any] | None = Depends(get_current_user_optional),
) -> None:
    """Router dependency: the read-only demo account can't save, edit or delete anything."""
    if (
        not user
        or not user.get("is_demo")
        or request.method in SAFE_METHODS
        or request.url.path in DEMO_ALLOWED_WRITES
    ):
        return
    logger.info("Blocked demo account write: %s %s", request.method, request.url.path)
    if request.url.path.startswith("/dashboard/chat/"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="الحساب التجريبي للعرض فقط")
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/dashboard?msg=demo_readonly"},
    )
