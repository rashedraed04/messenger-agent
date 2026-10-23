"""
Integration and route tests for dashboard authentication and pages.
"""

from unittest.mock import MagicMock

import pytest

from app.dashboard.middleware import get_current_user_optional, require_auth
from app.dependencies import get_db
from app.main import app


def test_unauthenticated_dashboard_redirects_to_login(client):
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/auth/login"


def test_login_page_renders_html(client):
    res = client.get("/auth/login")
    assert res.status_code == 200
    assert "تسجيل الدخول" in res.text


def test_dev_login_sets_cookie(client):
    res = client.post(
        "/auth/login",
        data={"email": "admin@example.com", "password": "admin123"},
        follow_redirects=False,
    )
    assert res.status_code == 303
    assert res.headers["location"] == "/dashboard"
    assert "dev_user" in res.headers.get("set-cookie", "")


@pytest.fixture
def auth_client(client):
    """Client with authenticated user dependency override and mock db."""
    mock_db = MagicMock()
    # Configure mock responses for select/order queries
    mock_query = MagicMock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.gte.return_value = mock_query
    mock_query.lte.return_value = mock_query
    mock_query.neq.return_value = mock_query
    mock_query.in_.return_value = mock_query
    mock_query.or_.return_value = mock_query
    mock_query.order.return_value = mock_query
    mock_query.range.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=[], count=0)

    mock_db.table.return_value = mock_query

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_auth] = lambda: {
        "id": "test-admin",
        "email": "admin@example.com",
        "store_id": "00000000-0000-0000-0000-000000000001",
    }
    yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_auth, None)


def test_dashboard_pages_render_authenticated(auth_client):
    pages = [
        "/dashboard",
        "/dashboard/products",
        "/dashboard/products/new",
        "/dashboard/chat",
        "/dashboard/faqs",
        "/dashboard/reports",
        "/dashboard/settings",
        "/dashboard/setup",
    ]

    for page in pages:
        res = auth_client.get(page)
        assert res.status_code == 200, f"Page {page} returned {res.status_code}"
        assert "متجر التقوى" in res.text, f"Page {page} missing brand name"


@pytest.mark.parametrize("path", [
    "/dashboard/orders",
    "/dashboard/orders/some-id/print",
    "/dashboard/customers",
    "/dashboard/delivery-zones",
    "/dashboard/conversations",
    "/dashboard/conversations/some-id",
])
def test_removed_pages_are_gone(auth_client, path):
    assert auth_client.get(path).status_code == 404


def test_overview_shows_bot_toggle(auth_client):
    res = auth_client.get("/dashboard")
    assert 'action="/dashboard/bot-toggle"' in res.text
    assert "إيقاف البوت" in res.text  # no setting saved yet means the bot is on


@pytest.mark.parametrize("form, value, msg", [
    ({"enabled": "true"}, "true", "bot_on"),
    ({}, "false", "bot_off"),
])
def test_bot_toggle_saves_setting(auth_client, form, value, msg):
    mock_db = app.dependency_overrides[get_db]()
    res = auth_client.post("/dashboard/bot-toggle", data=form, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == f"/dashboard?msg={msg}"
    saved = [c for c in mock_db.table.return_value.upsert.call_args_list]
    assert saved and saved[-1].args[0]["setting_key"] == "bot_enabled"
    assert saved[-1].args[0]["setting_value"] == value


def test_reports_page_shows_toggle(auth_client):
    res = auth_client.get("/dashboard/reports")
    assert 'action="/dashboard/reports/toggle"' in res.text
    assert "إيقاف التقرير اليومي" in res.text  # no row saved yet means reports are on


@pytest.mark.parametrize("form, value, msg", [
    ({"enabled": "true"}, True, "report_on"),
    ({}, False, "report_off"),
])
def test_report_toggle_saves_setting(auth_client, form, value, msg):
    mock_db = app.dependency_overrides[get_db]()
    res = auth_client.post("/dashboard/reports/toggle", data=form, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == f"/dashboard/reports?msg={msg}"
    saved = mock_db.table.return_value.upsert.call_args_list
    assert saved and saved[-1].args[0]["daily_report_enabled"] is value
    assert saved[-1].args[0]["channel"] == "telegram"


@pytest.fixture
def demo_client(client):
    mock_db = MagicMock()
    mock_query = MagicMock()
    for name in ("select", "eq", "gte", "lte", "neq", "in_", "or_", "order", "range", "limit", "upsert", "insert", "update", "delete"):
        getattr(mock_query, name).return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=[], count=0)
    mock_db.table.return_value = mock_query
    demo_user = {"id": "demo-1", "email": "user@test.com", "store_id": "00000000-0000-0000-0000-000000000001", "is_demo": True}
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[require_auth] = lambda: demo_user
    app.dependency_overrides[get_current_user_optional] = lambda: demo_user
    yield client, mock_db
    for dep in (get_db, require_auth, get_current_user_optional):
        app.dependency_overrides.pop(dep, None)


def test_demo_account_sees_banner(demo_client):
    client, _ = demo_client
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert 'id="demo-banner"' in res.text


@pytest.mark.parametrize("path", [
    "/dashboard/bot-toggle",
    "/dashboard/settings",
    "/dashboard/products/new",
    "/dashboard/faqs/new",
    "/dashboard/reports/send-now",
    "/dashboard/reports/toggle",
    "/dashboard/account/password",
    "/dashboard/account/email",
])
def test_demo_account_cannot_change_anything(demo_client, path):
    client, mock_db = demo_client
    res = client.post(path, data={"x": "1"}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/dashboard?msg=demo_readonly"
    assert not mock_db.table.return_value.upsert.called
    assert not mock_db.table.return_value.insert.called
    assert not mock_db.table.return_value.update.called
    assert not mock_db.table.return_value.delete.called


def test_demo_account_cannot_toggle_handoff(demo_client):
    client, _ = demo_client
    res = client.post("/dashboard/chat/handoff-toggle", json={"session_id": "sim_x", "is_handoff": True})
    assert res.status_code == 403
