"""
Tests for public customer storefront at GET / and GET /api/public/products.
Verifies RTL showcase, search, category filters, and zero price leaks.
"""

import re
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient
from app.dependencies import get_db
from app.main import app

STORE_ID = "00000000-0000-0000-0000-000000000001"

PRODUCTS = [
    {
        "id": "p-001", "store_id": STORE_ID, "name_ar": "سوفاج ديور", "name_en": "Dior Sauvage",
        "brand": "Dior", "category": "رجالي", "size_ml": 100, "price_jod": 95,
        "tags": "برغموت، عنبر", "description_ar": "عطر رجالي منعش", "product_type": "عطور ومسك",
        "is_active": True, "in_stock": True, "stock_quantity": 10, "sort_order": 1, "image_url": None,
    },
    {
        "id": "p-002", "store_id": STORE_ID, "name_ar": "مسبحة كهرمان", "name_en": "Amber Misbaha",
        "brand": "", "category": "للجنسين", "size_ml": None, "price_jod": 20,
        "tags": "كهرمان", "description_ar": "مسبحة 33 حبة", "product_type": None,
        "is_active": True, "in_stock": True, "stock_quantity": 5, "sort_order": 2, "image_url": None,
    },
]


class FakeProductsQuery:
    """Just enough of the Supabase query builder to filter PRODUCTS like the database."""

    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, column, value):
        self.rows = [r for r in self.rows if r.get(column) == value]
        return self

    def or_(self, expression):
        terms = {t.lower() for t in re.findall(r'ilike\."%(.*?)%"', expression)}
        self.rows = [
            r for r in self.rows
            if any(t in str(r.get(col) or "").lower() for col in ("name_ar", "name_en", "brand", "tags") for t in terms)
        ]
        return self

    def order(self, *_args, **_kwargs):
        return self

    def range(self, start, end):
        self.rows = self.rows[start:end + 1]
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows, count=len(self.rows))


class FakeDB:
    """Serves PRODUCTS; every other table fails, so categories and types use their defaults."""

    def table(self, name):
        if name == "products":
            return FakeProductsQuery(PRODUCTS)
        raise ConnectionError(f"no table {name} in tests")


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = lambda: FakeDB()
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def test_public_storefront_page_renders_html(client: TestClient):
    """Test that GET / returns a 200 OK and renders the luxury Arabic storefront."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text

    # Arabic RTL layout checks
    assert 'dir="rtl"' in html
    assert 'lang="ar"' in html

    # Catalog checks
    assert "سوفاج ديور" in html and "مسبحة كهرمان" in html
    assert "اطلب عبر ماسنجر" in html or "استفسر عن السعر" in html

    # Category filters present
    assert "رجالي" in html
    assert "نسائي" in html
    assert "للجنسين" in html
    assert "شرقي" in html

    # CRITICAL SECURITY REQUIREMENT: No prices anywhere in storefront HTML
    assert "JOD" not in html
    assert "د.أ" not in html
    assert "دينار" not in html
    assert "price_jod" not in html


def test_public_api_products_endpoint(client: TestClient):
    """Test that GET /api/public/products returns products without any price information."""
    response = client.get("/api/public/products")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    products = data["products"]
    assert isinstance(products, list)
    assert len(products) > 0

    # Verify that CRITICAL price_jod field is stripped from all products
    for item in products:
        assert "price_jod" not in item, f"Found price_jod in public item: {item.get('name_ar')}"
        assert "price" not in item, f"Found price in public item: {item.get('name_ar')}"
        assert "name_ar" in item
        assert "brand" in item
        assert "category" in item


def test_public_storefront_category_filtering(client: TestClient):
    """Test filtering by category on GET / and /api/public/products."""
    res_category = client.get("/api/public/products?category=رجالي")
    assert res_category.status_code == 200
    data = res_category.json()
    men_perfumes = data["products"]
    assert len(men_perfumes) > 0
    for p in men_perfumes:
        assert p["category"] == "رجالي"
        assert "price_jod" not in p


def test_public_storefront_search(client: TestClient):
    """Test searching products on /api/public/products."""
    res_search = client.get("/api/public/products?q=ديور")
    assert res_search.status_code == 200
    data = res_search.json()
    results = data["products"]
    assert len(results) > 0
    assert any("ديور" in p["name_ar"] or "Dior" in p["brand"] for p in results)
    for p in results:
        assert "price_jod" not in p


def test_public_results_partial_for_live_search(client: TestClient):
    """The live-search fragment returns only the grid, with no prices."""
    res = client.get("/partials/products?q=ديور")
    assert res.status_code == 200
    html = res.text
    assert "<html" not in html
    assert 'class="perfume-card"' in html
    assert "د.أ" not in html
    assert "price_jod" not in html


def test_public_search_with_reserved_characters(client: TestClient):
    res = client.get('/partials/products', params={"q": 'a,b(c).d:"%*_'})
    assert res.status_code == 200


def test_product_detail_page(client: TestClient):
    """Detail page shows notes, size and Messenger CTA, never a price."""
    res = client.get("/perfume/p-001")
    assert res.status_code == 200
    html = res.text
    assert "النوتات العطرية" in html
    assert "مل" in html
    assert "https://m.me/" in html
    assert "د.أ" not in html
    assert "JOD" not in html
    assert "price_jod" not in html


def test_product_detail_unknown_returns_404(client: TestClient):
    res = client.get("/perfume/does-not-exist")
    assert res.status_code == 404
    assert "غير متوفر" in res.text


def test_storefront_cards_link_to_detail_page(client: TestClient):
    res = client.get("/")
    assert 'href="/perfume/' in res.text


def test_privacy_policy_page(client: TestClient):
    """Meta needs a public privacy policy with data-deletion instructions."""
    res = client.get("/privacy")
    assert res.status_code == 200
    html = res.text
    assert "سياسة الخصوصية" in html
    assert 'id="data-deletion"' in html
    assert "m.me/" in html

    # Linked from every storefront page footer
    assert 'href="/privacy"' in client.get("/").text
