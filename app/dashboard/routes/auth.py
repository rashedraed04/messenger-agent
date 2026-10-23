"""
Dashboard authentication routes (login, logout, forgot/reset password, email confirmation).

Password reset and email change use Supabase Auth's built-in email links:
Supabase emails a one-time link that, once clicked, redirects back here with
the session in the URL fragment (#access_token=...). Fragments never reach
the server, so the reset page reads it in the browser and posts it with the
new password.
"""

import logging
from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import Settings, get_settings
from app.dashboard.auth_utils import (
    NO_STORE_HEADERS,
    clear_session_cookies,
    client_key,
    normalize_email,
    password_problem,
    set_session_cookie,
    supabase_error_message,
)
from app.dashboard.middleware import SESSION_COOKIE_NAME, get_current_user_optional
from app.dashboard.rate_limit import login_limiter, reset_email_limiter, reset_submit_limiter
from app.db.client import get_supabase_anon_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_ERROR = "البريد الإلكتروني أو كلمة المرور غير صحيحة."
TOO_MANY_ATTEMPTS = "محاولات كثيرة. يرجى الانتظار 15 دقيقة ثم المحاولة مرة أخرى."
INVALID_RESET_LINK = "رابط استعادة كلمة المرور غير صالح أو منتهي الصلاحية. اطلب رابطاً جديداً."
MAX_TOKEN_LENGTH = 4096

# Status notices shown on the login page (?msg=...); unknown keys are ignored
LOGIN_NOTICES = {
    "password_reset": "تم تعيين كلمة المرور الجديدة. سجّل الدخول بها الآن.",
    "logged_out": "تم تسجيل الخروج.",
}


def _render(request: Request, template: str, context: dict, status_code: int = 200):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        template,
        {"request": request, **context},
        status_code=status_code,
        headers=NO_STORE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
def show_login_page(
    request: Request,
    msg: str | None = Query(None),
    user: dict | None = Depends(get_current_user_optional),
):
    """Render login page. If already authenticated, redirect to /dashboard."""
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    return _render(request, "auth/login.html", {"error": None, "notice": LOGIN_NOTICES.get(msg or "")})


@router.post("/login")
def handle_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    settings: Settings = Depends(get_settings),
):
    """Authenticate user with Supabase Auth or test credentials."""
    email = email.strip()

    # Dev/demo login bypass for testing and initial non-cloud dev runs
    if settings.app_env in ("development", "testing") and (
        (email == "admin@example.com" and password in ("admin123", "admin1234"))
        or (email == "test@example.com" and password == "test1234")
    ):
        resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        resp.set_cookie(
            key="dev_user",
            value="true",
            httponly=True,
            samesite="lax",
        )
        return resp

    limit_key = f"{email.lower()}|{client_key(request)}"
    if login_limiter.is_limited(limit_key):
        return _render(
            request, "auth/login.html", {"error": TOO_MANY_ATTEMPTS, "email": email},
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    try:
        supabase = get_supabase_anon_client()
        auth_resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
        access_token = auth_resp.session.access_token if auth_resp.session else None
    except Exception as e:
        logger.warning("Supabase login failed: %s", type(e).__name__)
        access_token = None

    if not access_token:
        login_limiter.hit(limit_key)
        return _render(
            request, "auth/login.html", {"error": LOGIN_ERROR, "email": email},
            status.HTTP_400_BAD_REQUEST,
        )

    login_limiter.reset(limit_key)
    resp = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(resp, access_token, settings)
    return resp


@router.post("/logout")
def handle_logout(request: Request):
    """Revoke the Supabase session, clear session cookies and redirect to login."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        try:
            get_supabase_anon_client().auth.admin.sign_out(token, "local")
        except Exception as e:
            logger.info("Session revoke on logout failed: %s", type(e).__name__)

    resp = RedirectResponse(url="/auth/login?msg=logged_out", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookies(resp)
    return resp


# ---------------------------------------------------------------------------
# Forgot password → Supabase emails a one-time reset link
# ---------------------------------------------------------------------------
@router.get("/forgot-password", response_class=HTMLResponse)
def show_forgot_password(request: Request):
    return _render(request, "auth/forgot_password.html", {"sent": False, "error": None})


@router.post("/forgot-password", response_class=HTMLResponse)
def handle_forgot_password(
    request: Request,
    email: str = Form(...),
    settings: Settings = Depends(get_settings),
):
    """
    Send a password-reset link. The response is identical whether or not the
    address has an account, so the form cannot be used to discover accounts.
    """
    normalized = normalize_email(email)
    if not normalized:
        return _render(
            request, "auth/forgot_password.html",
            {"sent": False, "error": "يرجى إدخال بريد إلكتروني صالح.", "email": email.strip()},
            status.HTTP_400_BAD_REQUEST,
        )

    if not reset_email_limiter.is_limited(normalized):
        reset_email_limiter.hit(normalized)
        try:
            get_supabase_anon_client().auth.reset_password_for_email(
                normalized,
                {"redirect_to": f"{settings.app_base_url}/auth/reset-password"},
            )
        except Exception as e:
            logger.warning("Password reset email not sent: %s %s", type(e).__name__, getattr(e, "code", ""))

    return _render(request, "auth/forgot_password.html", {"sent": True, "error": None})


# ---------------------------------------------------------------------------
# Reset password (landing page of the emailed link)
# ---------------------------------------------------------------------------
@router.get("/reset-password", response_class=HTMLResponse)
def show_reset_password(request: Request):
    """Form page; its script picks up the recovery session from the URL fragment."""
    return _render(request, "auth/reset_password.html", {"error": None})


@router.post("/reset-password", response_class=HTMLResponse)
def handle_reset_password(
    request: Request,
    access_token: str = Form(""),
    refresh_token: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Set a new password using the recovery session from the emailed link."""

    def fail(error: str, status_code: int, tokens: tuple[str, str] | None = None):
        access, refresh = tokens or ("", "")
        return _render(
            request, "auth/reset_password.html",
            {"error": error, "link_invalid": tokens is None, "access_token": access, "refresh_token": refresh},
            status_code,
        )

    limit_key = client_key(request)
    if reset_submit_limiter.is_limited(limit_key):
        return fail(TOO_MANY_ATTEMPTS, status.HTTP_429_TOO_MANY_REQUESTS)

    if (
        not access_token or not refresh_token
        or len(access_token) > MAX_TOKEN_LENGTH or len(refresh_token) > MAX_TOKEN_LENGTH
    ):
        return fail(INVALID_RESET_LINK, status.HTTP_400_BAD_REQUEST)

    problem = password_problem(new_password, confirm_password)
    if problem:
        return fail(problem, status.HTTP_400_BAD_REQUEST, (access_token, refresh_token))

    reset_submit_limiter.hit(limit_key)
    supabase = get_supabase_anon_client()
    try:
        # Validates the token with Supabase (refreshing it if it has expired)
        session = supabase.auth.set_session(access_token, refresh_token).session
    except Exception as e:
        logger.info("Recovery session rejected: %s", type(e).__name__)
        session = None
    if not session:
        return fail(INVALID_RESET_LINK, status.HTTP_400_BAD_REQUEST)

    try:
        supabase.auth.update_user({"password": new_password})
    except Exception as e:
        logger.info("Password reset rejected by Supabase: %s %s", type(e).__name__, getattr(e, "code", ""))
        # set_session may have rotated the tokens; hand back the current pair
        return fail(
            supabase_error_message(e, "تعذر تغيير كلمة المرور. حاول مرة أخرى."),
            status.HTTP_400_BAD_REQUEST,
            (session.access_token, session.refresh_token),
        )

    # Sign out everywhere: the recovery session and any session an attacker may hold
    try:
        supabase.auth.sign_out({"scope": "global"})
    except Exception as e:
        logger.info("Global sign-out after reset failed: %s", type(e).__name__)

    reset_submit_limiter.reset(limit_key)
    resp = RedirectResponse(url="/auth/login?msg=password_reset", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookies(resp)
    return resp


# ---------------------------------------------------------------------------
# Email change confirmation (landing page of the emailed confirmation links)
# ---------------------------------------------------------------------------
@router.get("/email-confirmed", response_class=HTMLResponse)
def show_email_confirmed(request: Request):
    """Its script reads Supabase's result from the URL fragment and shows the outcome."""
    return _render(request, "auth/email_confirmed.html", {})
