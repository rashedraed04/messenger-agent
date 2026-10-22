"""
Shared helpers for dashboard auth flows (login, password reset, account changes).
"""

import re

from fastapi import Request
from fastapi.responses import Response

from app.config import Settings
from app.dashboard.middleware import SESSION_COOKIE_NAME

SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 72  # bcrypt ignores bytes beyond 72
EMAIL_MAX_LENGTH = 254
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Sent on every auth page/response: never cache pages carrying tokens or account data
NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def set_session_cookie(resp: Response, access_token: str, settings: Settings) -> None:
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=SESSION_MAX_AGE,
    )


def clear_session_cookies(resp: Response) -> None:
    resp.delete_cookie(SESSION_COOKIE_NAME)
    resp.delete_cookie("dev_user")


def normalize_email(email: str) -> str | None:
    """Lower-cased, trimmed email, or None if it is not a plausible address."""
    email = (email or "").strip().lower()
    if len(email) > EMAIL_MAX_LENGTH or not _EMAIL_RE.match(email):
        return None
    return email


def password_problem(new_password: str, confirm_password: str) -> str | None:
    """Arabic validation message for a new password, or None if acceptable."""
    if new_password != confirm_password:
        return "كلمتا المرور غير متطابقتين."
    if len(new_password) < PASSWORD_MIN_LENGTH:
        return f"كلمة المرور يجب أن تكون {PASSWORD_MIN_LENGTH} أحرف على الأقل."
    if len(new_password.encode("utf-8")) > PASSWORD_MAX_LENGTH:
        return "كلمة المرور طويلة جداً."
    if not (re.search(r"[A-Za-z؀-ۿ]", new_password) and re.search(r"\d", new_password)):
        return "كلمة المرور يجب أن تحتوي على أحرف وأرقام معاً."
    return None


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def supabase_error_message(exc: Exception, fallback: str) -> str:
    """Map known Supabase Auth error codes to Arabic messages; never leak raw errors."""
    code = getattr(exc, "code", None)
    messages = {
        "weak_password": "كلمة المرور ضعيفة. اختر كلمة مرور أقوى.",
        "same_password": "كلمة المرور الجديدة يجب أن تختلف عن الحالية.",
        "email_exists": "هذا البريد الإلكتروني مستخدم لحساب آخر.",
        "email_address_invalid": "البريد الإلكتروني غير صالح.",
        "over_email_send_rate_limit": "تم إرسال رسائل كثيرة. انتظر قليلاً ثم حاول مرة أخرى.",
        "over_request_rate_limit": "محاولات كثيرة. انتظر قليلاً ثم حاول مرة أخرى.",
        "reauthentication_needed": "يرجى تسجيل الخروج ثم الدخول من جديد والمحاولة مرة أخرى.",
        # Supabase returns this when its SMTP server (e.g. Gmail) rejects the message
        "unexpected_failure": "تعذر إرسال رسالة البريد. تحقق من إعدادات SMTP في Supabase (كلمة مرور التطبيق في Gmail).",
    }
    return messages.get(code, fallback)
