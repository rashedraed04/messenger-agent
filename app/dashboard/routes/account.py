"""
Dashboard account security: change login email and password.

Both changes require the current password. An email change only takes effect
after the admin clicks the confirmation link Supabase Auth emails out, which
proves ownership of the new address (e.g. a Gmail inbox).
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import Settings
from app.dashboard.auth_utils import (
    NO_STORE_HEADERS,
    normalize_email,
    password_problem,
    set_session_cookie,
    supabase_error_message,
)
from app.dashboard.middleware import require_auth
from app.dashboard.rate_limit import reauth_limiter
from app.db.client import get_supabase_anon_client
from app.dependencies import get_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/account", tags=["dashboard_account"])

WRONG_CURRENT_PASSWORD = "كلمة المرور الحالية غير صحيحة."
TOO_MANY_ATTEMPTS = "محاولات خاطئة كثيرة. يرجى الانتظار 15 دقيقة ثم المحاولة مرة أخرى."
DEV_ACCOUNT = "هذا حساب تجريبي محلي غير مرتبط بـ Supabase، لا يمكن تعديله."

NOTICES = {
    "email_pending": "تم إرسال رابط تأكيد إلى بريدك. لن يتغير البريد حتى تضغط على الرابط.",
    "password_changed": "تم تغيير كلمة المرور، وتم تسجيل الخروج من جميع الأجهزة الأخرى.",
}


def _render(request: Request, user: dict[str, Any], status_code: int = 200, **context: Any):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/account.html",
        {
            "request": request,
            "user": user,
            "active_page": "account",
            "notice": None,
            "email_error": None,
            "password_error": None,
            **context,
        },
        status_code=status_code,
        headers=NO_STORE_HEADERS,
    )


def _reauthenticate(user: dict[str, Any], current_password: str):
    """
    Sign in again with the current password on a fresh client.
    Returns (client, session) on success, or (None, error_message).
    """
    limit_key = str(user.get("id"))
    if reauth_limiter.is_limited(limit_key):
        return None, TOO_MANY_ATTEMPTS

    supabase = get_supabase_anon_client()
    try:
        auth_resp = supabase.auth.sign_in_with_password(
            {"email": user.get("email") or "", "password": current_password}
        )
        session = auth_resp.session
    except Exception as e:
        logger.info("Re-authentication failed: %s", type(e).__name__)
        session = None

    if not session or not session.user or session.user.id != user.get("id"):
        reauth_limiter.hit(limit_key)
        return None, WRONG_CURRENT_PASSWORD

    reauth_limiter.reset(limit_key)
    return supabase, session


@router.get("", response_class=HTMLResponse)
def show_account(
    request: Request,
    msg: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
):
    return _render(request, user, notice=NOTICES.get(msg or ""))


@router.post("/email", response_class=HTMLResponse)
def change_email(
    request: Request,
    new_email: str = Form(...),
    current_password: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    config: Settings = Depends(get_config),
):
    """Request an email change; Supabase emails a confirmation link."""

    def fail(error: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        return _render(request, user, status_code, email_error=error, new_email_value=new_email.strip())

    if user.get("is_dev"):
        return fail(DEV_ACCOUNT)

    normalized = normalize_email(new_email)
    if not normalized:
        return fail("يرجى إدخال بريد إلكتروني صالح.")
    if normalized == (user.get("email") or "").lower():
        return fail("هذا هو بريدك الحالي بالفعل.")

    supabase, session_or_error = _reauthenticate(user, current_password)
    if not supabase:
        return fail(session_or_error)

    try:
        supabase.auth.update_user(
            {"email": normalized},
            {"email_redirect_to": f"{config.app_base_url}/auth/email-confirmed"},
        )
    except Exception as e:
        logger.info("Email change rejected by Supabase: %s %s", type(e).__name__, getattr(e, "code", ""))
        return fail(supabase_error_message(e, "تعذر تغيير البريد الإلكتروني. حاول مرة أخرى."))
    finally:
        # Drop the session opened only to verify the password
        try:
            supabase.auth.sign_out({"scope": "local"})
        except Exception:
            pass

    return RedirectResponse(url="/dashboard/account?msg=email_pending", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/password", response_class=HTMLResponse)
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    config: Settings = Depends(get_config),
):
    """Change password, then sign out every other session."""

    def fail(error: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        return _render(request, user, status_code, password_error=error)

    if user.get("is_dev"):
        return fail(DEV_ACCOUNT)

    problem = password_problem(new_password, confirm_password)
    if problem:
        return fail(problem)
    if new_password == current_password:
        return fail("كلمة المرور الجديدة يجب أن تختلف عن الحالية.")

    supabase, session_or_error = _reauthenticate(user, current_password)
    if not supabase:
        return fail(session_or_error)
    session = session_or_error

    try:
        supabase.auth.update_user({"password": new_password})
    except Exception as e:
        logger.info("Password change rejected by Supabase: %s %s", type(e).__name__, getattr(e, "code", ""))
        try:
            supabase.auth.sign_out({"scope": "local"})
        except Exception:
            pass
        return fail(supabase_error_message(e, "تعذر تغيير كلمة المرور. حاول مرة أخرى."))

    # Keep only the fresh session (it becomes this browser's cookie); revoke the rest
    try:
        supabase.auth.sign_out({"scope": "others"})
    except Exception as e:
        logger.warning("Revoking other sessions failed: %s", type(e).__name__)

    resp = RedirectResponse(url="/dashboard/account?msg=password_changed", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(resp, session.access_token, config)
    return resp
