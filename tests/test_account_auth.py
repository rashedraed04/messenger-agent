"""
Tests for admin account security: forgot/reset password, change email, change password.
Supabase Auth is mocked; these verify routing, validation and security behaviour.
"""

from unittest.mock import MagicMock, patch

import pytest
from gotrue.errors import AuthApiError

from app.dashboard.middleware import require_auth
from app.dashboard.rate_limit import (
    login_limiter,
    reauth_limiter,
    reset_email_limiter,
    reset_submit_limiter,
)
from app.main import app

ADMIN = {
    "id": "test-admin",
    "email": "admin@gmail.com",
    "new_email": None,
    "store_id": "00000000-0000-0000-0000-000000000001",
}


@pytest.fixture(autouse=True)
def clear_limiters():
    for limiter in (login_limiter, reauth_limiter, reset_email_limiter, reset_submit_limiter):
        limiter.clear()
    yield


@pytest.fixture
def supabase_mock():
    """One mocked anon client shared by the auth and account routes."""
    mock = MagicMock()
    session = MagicMock(access_token="fresh-access", refresh_token="fresh-refresh")
    session.user.id = ADMIN["id"]
    mock.auth.sign_in_with_password.return_value = MagicMock(session=session)
    mock.auth.set_session.return_value = MagicMock(session=session)
    with patch("app.dashboard.routes.auth.get_supabase_anon_client", return_value=mock), \
         patch("app.dashboard.routes.account.get_supabase_anon_client", return_value=mock):
        yield mock


@pytest.fixture
def admin_client(client):
    app.dependency_overrides[require_auth] = lambda: dict(ADMIN)
    yield client
    app.dependency_overrides.pop(require_auth, None)


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------
def test_login_page_has_forgot_password_link_and_no_prefilled_password(client):
    res = client.get("/auth/login")
    assert res.status_code == 200
    assert 'href="/auth/forgot-password"' in res.text
    assert "admin123" not in res.text
    assert res.headers["cache-control"] == "no-store"


def test_login_notice_only_shows_whitelisted_messages(client):
    res = client.get("/auth/login", params={"msg": "<script>alert(1)</script>"})
    assert "<script>alert(1)</script>" not in res.text
    res = client.get("/auth/login", params={"msg": "password_reset"})
    assert "تم تعيين كلمة المرور الجديدة" in res.text


def test_supabase_login_sets_session_cookie(client, supabase_mock):
    res = client.post(
        "/auth/login", data={"email": "owner@gmail.com", "password": "Secret123"}, follow_redirects=False
    )
    assert res.status_code == 303
    assert "sb_access_token=fresh-access" in res.headers["set-cookie"]
    assert "httponly" in res.headers["set-cookie"].lower()


def test_login_is_rate_limited_after_repeated_failures(client, supabase_mock):
    supabase_mock.auth.sign_in_with_password.side_effect = AuthApiError("bad", 400, "invalid_credentials")
    for _ in range(10):
        res = client.post("/auth/login", data={"email": "owner@gmail.com", "password": "wrong"})
        assert res.status_code == 400
    res = client.post("/auth/login", data={"email": "owner@gmail.com", "password": "wrong"})
    assert res.status_code == 429
    assert supabase_mock.auth.sign_in_with_password.call_count == 10


def test_logout_revokes_supabase_session(client, supabase_mock):
    client.cookies.set("sb_access_token", "old-token")
    res = client.post("/auth/logout", follow_redirects=False)
    assert res.status_code == 303
    supabase_mock.auth.admin.sign_out.assert_called_once_with("old-token", "local")


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------
def test_forgot_password_page_renders(client):
    res = client.get("/auth/forgot-password")
    assert res.status_code == 200
    assert 'action="/auth/forgot-password"' in res.text
    assert 'name="csrf_token"' in res.text


def test_forgot_password_sends_reset_email(client, supabase_mock):
    res = client.post("/auth/forgot-password", data={"email": "  Admin@Gmail.com "})
    assert res.status_code == 200
    assert 'id="forgot-sent"' in res.text
    supabase_mock.auth.reset_password_for_email.assert_called_once_with(
        "admin@gmail.com", {"redirect_to": "http://localhost:8080/auth/reset-password"}
    )


def test_forgot_password_response_does_not_reveal_unknown_accounts(client, supabase_mock):
    ok = client.post("/auth/forgot-password", data={"email": "admin@gmail.com"})
    supabase_mock.auth.reset_password_for_email.side_effect = AuthApiError("User not found", 400, "user_not_found")
    unknown = client.post("/auth/forgot-password", data={"email": "nobody@gmail.com"})
    assert ok.status_code == unknown.status_code == 200
    assert 'id="forgot-sent"' in unknown.text
    assert "not found" not in unknown.text


def test_forgot_password_rejects_invalid_email(client, supabase_mock):
    res = client.post("/auth/forgot-password", data={"email": "not-an-email"})
    assert res.status_code == 400
    supabase_mock.auth.reset_password_for_email.assert_not_called()


def test_forgot_password_limits_emails_per_address(client, supabase_mock):
    for _ in range(5):
        res = client.post("/auth/forgot-password", data={"email": "admin@gmail.com"})
        assert res.status_code == 200
    assert supabase_mock.auth.reset_password_for_email.call_count == 3


def test_forgot_password_requires_csrf(client, supabase_mock):
    res = client.post(
        "/auth/forgot-password", data={"email": "admin@gmail.com"}, headers={"X-CSRF-Token": ""}
    )
    assert res.status_code == 403
    supabase_mock.auth.reset_password_for_email.assert_not_called()


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------
RESET_FORM = {
    "access_token": "recovery-access",
    "refresh_token": "recovery-refresh",
    "new_password": "NewPass123",
    "confirm_password": "NewPass123",
}


def test_reset_password_page_renders_with_fragment_handler(client):
    res = client.get("/auth/reset-password")
    assert res.status_code == 200
    assert 'id="reset-form"' in res.text
    assert "history.replaceState" in res.text
    assert res.headers["referrer-policy"] == "no-referrer"


def test_reset_password_success(client, supabase_mock):
    res = client.post("/auth/reset-password", data=RESET_FORM, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login?msg=password_reset"
    supabase_mock.auth.set_session.assert_called_once_with("recovery-access", "recovery-refresh")
    supabase_mock.auth.update_user.assert_called_once_with({"password": "NewPass123"})
    supabase_mock.auth.sign_out.assert_called_once_with({"scope": "global"})


def test_reset_password_without_tokens_is_rejected(client, supabase_mock):
    res = client.post("/auth/reset-password", data={**RESET_FORM, "access_token": ""})
    assert res.status_code == 400
    assert 'href="/auth/forgot-password"' in res.text
    supabase_mock.auth.update_user.assert_not_called()


def test_reset_password_with_invalid_token_is_rejected(client, supabase_mock):
    supabase_mock.auth.set_session.side_effect = AuthApiError("invalid JWT", 401, "bad_jwt")
    res = client.post("/auth/reset-password", data=RESET_FORM)
    assert res.status_code == 400
    assert "غير صالح أو منتهي" in res.text
    supabase_mock.auth.update_user.assert_not_called()


@pytest.mark.parametrize(
    "overrides",
    [
        {"confirm_password": "Different123"},
        {"new_password": "short1", "confirm_password": "short1"},
        {"new_password": "onlyletters", "confirm_password": "onlyletters"},
    ],
)
def test_reset_password_validates_new_password_and_keeps_form(client, supabase_mock, overrides):
    res = client.post("/auth/reset-password", data={**RESET_FORM, **overrides})
    assert res.status_code == 400
    assert 'value="recovery-access"' in res.text
    supabase_mock.auth.set_session.assert_not_called()


def test_reset_password_supabase_rejection_returns_rotated_tokens(client, supabase_mock):
    supabase_mock.auth.update_user.side_effect = AuthApiError("weak", 422, "weak_password")
    res = client.post("/auth/reset-password", data=RESET_FORM)
    assert res.status_code == 400
    assert "كلمة المرور ضعيفة" in res.text
    assert 'value="fresh-access"' in res.text


# ---------------------------------------------------------------------------
# Account page: change email / password
# ---------------------------------------------------------------------------
def test_account_page_requires_login(client):
    res = client.get("/dashboard/account", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"


def test_account_page_renders(admin_client):
    res = admin_client.get("/dashboard/account")
    assert res.status_code == 200
    assert "admin@gmail.com" in res.text
    assert 'action="/dashboard/account/email"' in res.text
    assert 'action="/dashboard/account/password"' in res.text


def test_change_email_sends_confirmation(admin_client, supabase_mock):
    res = admin_client.post(
        "/dashboard/account/email",
        data={"new_email": "New.Owner@Gmail.com", "current_password": "OldPass123"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/dashboard/account?msg=email_pending"
    supabase_mock.auth.sign_in_with_password.assert_called_once_with(
        {"email": "admin@gmail.com", "password": "OldPass123"}
    )
    supabase_mock.auth.update_user.assert_called_once_with(
        {"email": "new.owner@gmail.com"},
        {"email_redirect_to": "http://localhost:8080/auth/email-confirmed"},
    )


def test_change_email_requires_correct_current_password(admin_client, supabase_mock):
    supabase_mock.auth.sign_in_with_password.side_effect = AuthApiError("bad", 400, "invalid_credentials")
    res = admin_client.post(
        "/dashboard/account/email", data={"new_email": "new@gmail.com", "current_password": "wrong"}
    )
    assert res.status_code == 400
    assert "كلمة المرور الحالية غير صحيحة" in res.text
    supabase_mock.auth.update_user.assert_not_called()


def test_change_email_rejects_same_or_invalid_address(admin_client, supabase_mock):
    for email in ("ADMIN@gmail.com", "bad-address"):
        res = admin_client.post(
            "/dashboard/account/email", data={"new_email": email, "current_password": "OldPass123"}
        )
        assert res.status_code == 400
    supabase_mock.auth.sign_in_with_password.assert_not_called()


def test_change_email_reports_address_in_use(admin_client, supabase_mock):
    supabase_mock.auth.update_user.side_effect = AuthApiError("exists", 422, "email_exists")
    res = admin_client.post(
        "/dashboard/account/email", data={"new_email": "taken@gmail.com", "current_password": "OldPass123"}
    )
    assert res.status_code == 400
    assert "مستخدم لحساب آخر" in res.text


def test_change_password_success_rotates_session(admin_client, supabase_mock):
    res = admin_client.post(
        "/dashboard/account/password",
        data={"current_password": "OldPass123", "new_password": "NewPass456", "confirm_password": "NewPass456"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/dashboard/account?msg=password_changed"
    supabase_mock.auth.update_user.assert_called_once_with({"password": "NewPass456"})
    supabase_mock.auth.sign_out.assert_called_once_with({"scope": "others"})
    assert "sb_access_token=fresh-access" in res.headers["set-cookie"]


def test_change_password_wrong_current_is_rate_limited(admin_client, supabase_mock):
    supabase_mock.auth.sign_in_with_password.side_effect = AuthApiError("bad", 400, "invalid_credentials")
    data = {"current_password": "guess", "new_password": "NewPass456", "confirm_password": "NewPass456"}
    for _ in range(5):
        assert admin_client.post("/dashboard/account/password", data=data).status_code == 400
    res = admin_client.post("/dashboard/account/password", data=data)
    assert "محاولات خاطئة كثيرة" in res.text
    assert supabase_mock.auth.sign_in_with_password.call_count == 5


def test_change_password_validation(admin_client, supabase_mock):
    cases = [
        {"current_password": "OldPass123", "new_password": "NewPass456", "confirm_password": "Other456"},
        {"current_password": "OldPass123", "new_password": "OldPass123", "confirm_password": "OldPass123"},
    ]
    for data in cases:
        assert admin_client.post("/dashboard/account/password", data=data).status_code == 400
    supabase_mock.auth.sign_in_with_password.assert_not_called()


def test_account_changes_require_csrf(admin_client, supabase_mock):
    res = admin_client.post(
        "/dashboard/account/password",
        data={"current_password": "OldPass123", "new_password": "NewPass456", "confirm_password": "NewPass456"},
        headers={"X-CSRF-Token": "forged-token-value-123456"},
    )
    assert res.status_code == 403
    supabase_mock.auth.sign_in_with_password.assert_not_called()


def test_dev_account_cannot_change_credentials(client, supabase_mock):
    app.dependency_overrides[require_auth] = lambda: {**ADMIN, "is_dev": True}
    try:
        res = client.post(
            "/dashboard/account/email", data={"new_email": "new@gmail.com", "current_password": "x"}
        )
        assert res.status_code == 400
        supabase_mock.auth.sign_in_with_password.assert_not_called()
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_email_confirmed_page_renders(client):
    res = client.get("/auth/email-confirmed")
    assert res.status_code == 200
    assert 'id="confirm-done"' in res.text
