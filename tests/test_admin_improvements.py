"""
Tests for CSRF protection, safe search filters, pagination, categories
management and the human-handoff overview card.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.dashboard.middleware import require_auth
from app.db.repositories.search import build_ilike_or_filter, clean_search_term
from app.dependencies import get_db
from app.main import app

STORE_ID = "00000000-0000-0000-0000-000000000001"
CATEGORY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def make_mock_db(data=None, count=0):
    """MagicMock Supabase client whose every query chain returns `data`."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    for method in ("select", "insert", "update", "delete", "eq", "gte", "lte", "neq",
                   "in_", "or_", "order", "range", "limit"):
        getattr(mock_query, method).return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=data or [], count=count)
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.fixture
def authed(client):
    """Return a function installing a mock db + authenticated admin on `client`."""
    def install(data=None, count=0):
        mock_db, mock_query = make_mock_db(data, count)
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[require_auth] = lambda: {
            "id": "test-admin", "email": "admin@example.com", "store_id": STORE_ID,
        }
        return mock_db, mock_query

    yield install
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_auth, None)


# ---------------------------------------------------------------------------
# Search filter safety
# ---------------------------------------------------------------------------
def test_clean_search_term_strips_wildcards_and_quotes():
    assert clean_search_term('  ديور  %_*"\\ سوفاج ') == "ديور سوفاج"
    assert clean_search_term(None) == ""
    assert clean_search_term("%%%") == ""
    assert len(clean_search_term("a" * 500)) == 100


def test_build_ilike_or_filter_quotes_reserved_characters():
    term = clean_search_term("Dior, (Sauvage).v2:")
    result = build_ilike_or_filter(["name_ar", "brand"], term)
    assert result == 'name_ar.ilike."%Dior, (Sauvage).v2:%",brand.ilike."%Dior, (Sauvage).v2:%"'


def test_products_search_with_special_characters_does_not_break(client, authed):
    _, mock_query = authed()
    res = client.get("/dashboard/products", params={"q": "a,b(c).d"})
    assert res.status_code == 200
    filter_arg = mock_query.or_.call_args[0][0]
    assert 'name_ar.ilike."%a,b(c).d%"' in filter_arg


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------
def test_dashboard_pages_include_csrf_token(client, authed):
    authed()
    res = client.get("/dashboard/faqs")
    token = client.cookies.get("csrf_token")
    assert token
    assert f'name="csrf_token" value="{token}"' in res.text
    assert f'<meta name="csrf-token" content="{token}">' in res.text


def test_post_without_csrf_token_is_rejected(test_settings, authed):
    authed()
    with TestClient(app) as raw_client:
        raw_client.get("/auth/login")  # has cookie, but sends no token
        res = raw_client.post("/dashboard/products/x/delete", follow_redirects=False)
        assert res.status_code == 403

        res = raw_client.post(
            "/dashboard/products/x/delete",
            data={"csrf_token": "wrong-token-value-1234567890"},
            follow_redirects=False,
        )
        assert res.status_code == 403


def test_post_with_csrf_form_field_is_accepted(test_settings, authed):
    authed()
    with TestClient(app) as raw_client:
        raw_client.get("/auth/login")
        token = raw_client.cookies.get("csrf_token")
        res = raw_client.post(
            "/dashboard/products/x/delete",
            data={"csrf_token": token},
            follow_redirects=False,
        )
        assert res.status_code == 303


def test_login_requires_csrf_token():
    with TestClient(app) as raw_client:
        res = raw_client.post(
            "/auth/login",
            data={"email": "admin@example.com", "password": "admin123"},
            follow_redirects=False,
        )
        assert res.status_code == 403


def test_public_routes_are_not_csrf_protected():
    with TestClient(app) as raw_client:
        res = raw_client.get("/api/public/products")
        assert res.status_code == 200
        assert "csrf_token" not in res.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------
def test_products_second_page_uses_offset(client, authed):
    _, mock_query = authed([])
    res = client.get("/dashboard/products", params={"page": 2})
    assert res.status_code == 200
    mock_query.range.assert_called_with(25, 50)


def test_invalid_page_number_is_clamped(client, authed):
    _, mock_query = authed([])
    res = client.get("/dashboard/products", params={"page": -3})
    assert res.status_code == 200
    mock_query.range.assert_called_with(0, 25)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
def test_categories_page_renders(client, authed):
    authed([{"id": CATEGORY_ID, "name_ar": "رجالي", "show_in_filter": True, "sort_order": 1, "category": "رجالي"}])
    res = client.get("/dashboard/categories")
    assert res.status_code == 200
    assert "فئات المنتجات" in res.text
    assert "رجالي" in res.text


def test_create_category_inserts_row(client, authed):
    _, mock_query = authed([])
    res = client.post("/dashboard/categories/new", data={"name_ar": "  عطور   فرنسية "}, follow_redirects=False)
    assert res.status_code == 303
    assert res.headers["location"] == "/dashboard/categories?msg=created"
    inserted = mock_query.insert.call_args[0][0]
    assert inserted["name_ar"] == "عطور فرنسية"
    assert inserted["store_id"] == STORE_ID


def test_create_category_rejects_empty_name(client, authed):
    authed([])
    res = client.post("/dashboard/categories/new", data={"name_ar": "   "}, follow_redirects=False)
    assert res.headers["location"] == "/dashboard/categories?error=invalid_name"


def test_delete_category_in_use_is_refused(client, authed):
    _, mock_query = authed([{"id": CATEGORY_ID, "name_ar": "رجالي", "category": "رجالي"}])
    res = client.post(f"/dashboard/categories/{CATEGORY_ID}/delete", follow_redirects=False)
    assert res.headers["location"] == "/dashboard/categories?error=in_use"
    mock_query.delete.assert_not_called()


def test_product_form_lists_categories_from_db(client, authed):
    authed([{"id": CATEGORY_ID, "name_ar": "عطور فرنسية", "show_in_filter": True}])
    res = client.get("/dashboard/products/new")
    assert res.status_code == 200
    assert '<option value="عطور فرنسية"' in res.text


def test_categories_page_handles_missing_table(client, authed):
    _, mock_query = authed([])
    mock_query.execute.side_effect = Exception('relation "product_categories" does not exist')
    res = client.get("/dashboard/categories")
    assert res.status_code == 200
    assert "003_product_categories.sql" in res.text


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def test_overview_has_only_recent_orders_and_quick_actions(client, authed):
    authed([], count=3)
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert "آخر الطلبات" in res.text and "إجراءات سريعة" in res.text
    for removed in ("طلبات اليوم", "محادثات نشطة", "بانتظار موظف", "تنبيه المخزون", "/dashboard/conversations"):
        assert removed not in res.text


def test_product_form_has_no_quantity_field(client, authed):
    authed([])
    res = client.get("/dashboard/products/new")
    assert res.status_code == 200
    assert "stock_quantity" not in res.text and "الكمية بالمخزون" not in res.text
