"""
Integration and route tests for dashboard authentication and pages.
"""

from unittest.mock import MagicMock
import pytest
from app.dashboard.middleware import require_auth
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
        data={"email": "admin@perfumestore.jo", "password": "admin123"},
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
        "email": "admin@perfumestore.jo",
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
