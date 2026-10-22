"""
CSRF protection for dashboard and auth forms (double-submit cookie pattern).

- CSRFCookieMiddleware issues a random token cookie on /dashboard and /auth
  requests and exposes it to templates via request.state.csrf_token.
- csrf_protect (router dependency) rejects unsafe requests unless the same
  token is sent back in the `csrf_token` form field or `X-CSRF-Token` header.
"""

import secrets
from http.cookies import SimpleCookie

from fastapi import HTTPException, Request, status
from markupsafe import Markup, escape
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
PROTECTED_PATH_PREFIXES = ("/dashboard", "/auth")
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


def _is_valid_token(token: str | None) -> bool:
    return bool(token) and 20 <= len(token) <= 128 and token.replace("-", "").replace("_", "").isalnum()


class CSRFCookieMiddleware:
    """Pure ASGI middleware that guarantees a CSRF token cookie exists."""

    def __init__(self, app: ASGIApp, secure: bool = False):
        self.app = app
        self.secure = secure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(PROTECTED_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        token = HTTPConnection(scope).cookies.get(CSRF_COOKIE_NAME)
        is_new = not _is_valid_token(token)
        if is_new:
            token = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csrf_token"] = token

        if not is_new:
            await self.app(scope, receive, send)
            return

        cookie = SimpleCookie()
        cookie[CSRF_COOKIE_NAME] = token
        cookie[CSRF_COOKIE_NAME]["path"] = "/"
        cookie[CSRF_COOKIE_NAME]["samesite"] = "Lax"
        cookie[CSRF_COOKIE_NAME]["httponly"] = True
        cookie[CSRF_COOKIE_NAME]["max-age"] = CSRF_COOKIE_MAX_AGE
        if self.secure:
            cookie[CSRF_COOKIE_NAME]["secure"] = True
        cookie_header = cookie.output(header="").strip()

        async def send_with_cookie(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message).append("set-cookie", cookie_header)
            await send(message)

        await self.app(scope, receive, send_with_cookie)


async def csrf_protect(request: Request) -> None:
    """Router dependency: verify the CSRF token on state-changing requests."""
    if request.method in SAFE_METHODS:
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    sent_token = request.headers.get(CSRF_HEADER_NAME)
    if not sent_token and request.headers.get("content-type", "").startswith(FORM_CONTENT_TYPES):
        form = await request.form()
        sent_token = form.get(CSRF_FORM_FIELD)

    if (
        not cookie_token
        or not isinstance(sent_token, str)
        or not secrets.compare_digest(sent_token, cookie_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="انتهت صلاحية الجلسة أو الطلب غير موثوق. يرجى تحديث الصفحة والمحاولة مرة أخرى.",
        )


def get_csrf_token(request: Request) -> str:
    """Template helper: current request's CSRF token ('' outside protected paths)."""
    return getattr(request.state, "csrf_token", "") or ""


def csrf_input(request: Request) -> Markup:
    """Template helper: hidden input carrying the CSRF token for POST forms."""
    return Markup(
        f'<input type="hidden" name="{CSRF_FORM_FIELD}" value="{escape(get_csrf_token(request))}">'
    )
