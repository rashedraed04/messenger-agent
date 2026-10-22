"""
Tests for admin customization: product types, category rename/reorder,
storefront branding settings, the storefront type filter and the
pre-migration fallback when products.product_type does not exist yet.
"""

from unittest.mock import MagicMock
import pytest

from app.dashboard.middleware import require_auth
from app.db.repositories.product_types import (
    DEFAULT_TYPES,
    clean_type_fields,
    describe_product,
    format_size,
    load_types_by_name,
    reorder_rows,
)
from app.db.repositories.products import ProductRepository
from app.dependencies import get_db
from app.main import app
from app.models.product import ProductCreate
from app.services.branding import build_branding, get_branding, invalidate_branding
from app.services.product_photos import detect_photo_type

STORE_ID = "00000000-0000-0000-0000-000000000001"
TYPE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CATEGORY_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


def make_mock_db(data=None):
    mock_db = MagicMock()
    mock_query = MagicMock()
    for method in ("select", "insert", "update", "delete", "upsert", "eq", "gte", "lte", "neq",
                   "in_", "or_", "order", "range", "limit"):
        getattr(mock_query, method).return_value = mock_query
    mock_query.execute.return_value = MagicMock(data=data or [], count=0)
    mock_db.table.return_value = mock_query
    return mock_db, mock_query


@pytest.fixture
def authed(client):
    def install(data=None):
        mock_db, mock_query = make_mock_db(data)
        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[require_auth] = lambda: {
            "id": "test-admin", "email": "admin@example.jo", "store_id": STORE_ID,
        }
        return mock_db, mock_query

    yield install
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_auth, None)


# ---------------------------------------------------------------------------
# Product type helpers
# ---------------------------------------------------------------------------
def test_clean_type_fields_normalises_and_validates():
    fields = clean_type_fields("  سجاد   صلاة ", "rug", " المقاس ", "سم", "")
    assert fields == {
        "name_ar": "سجاد صلاة", "visual": "rug",
        "size_label": "المقاس", "size_unit": "سم", "details_label": "المميزات",
    }
    assert clean_type_fields("   ", "rug", None, None, None) is None
    # Unknown visual falls back to the gift box; no size label drops the unit
    fields = clean_type_fields("هدايا", "rocket", "", "مل", "المحتويات")
    assert fields["visual"] == "gift"
    assert fields["size_unit"] is None


def test_describe_product_uses_type_then_legacy_rules():
    types = {"سجاد صلاة": {"visual": "rug", "size_label": "المقاس", "size_unit": "سم", "details_label": "المميزات"}}
    rug = {"product_type": "سجاد صلاة", "size_ml": "120×80"}
    info = describe_product(rug, types)
    assert info["visual"] == "rug"
    assert format_size(rug, info) == "120×80 سم"

    legacy_perfume = {"size_ml": "100"}
    info = describe_product(legacy_perfume, types)
    assert info["visual"] == "bottle"
    assert format_size(legacy_perfume, info) == "100 مل"

    assert describe_product({"product_type": "غير معروف"}, types)["visual"] == "gift"
    assert format_size({"size_ml": ""}, info) == ""


def test_load_types_by_name_never_raises():
    broken = MagicMock()
    broken.table.side_effect = Exception("relation does not exist")
    types = load_types_by_name(broken, STORE_ID)
    assert set(types) == {t["name_ar"] for t in DEFAULT_TYPES}
    assert load_types_by_name(None, STORE_ID)


def test_reorder_rows_swaps_neighbours():
    mock_db, mock_query = make_mock_db()
    rows = [{"id": "a", "sort_order": 1}, {"id": "b", "sort_order": 2}, {"id": "c", "sort_order": 3}]
    assert reorder_rows(mock_db, "product_types", STORE_ID, rows, "b", -1) is True
    updates = [c.args[0] for c in mock_query.update.call_args_list]
    assert updates == [{"sort_order": 1}, {"sort_order": 2}]
    assert reorder_rows(mock_db, "product_types", STORE_ID, rows, "a", -1) is False


# ---------------------------------------------------------------------------
# Product types dashboard
# ---------------------------------------------------------------------------
def test_product_types_page_renders(client, authed):
    authed([{"id": TYPE_ID, "name_ar": "سجاد صلاة", "visual": "rug", "size_label": "المقاس",
             "size_unit": "سم", "details_label": "المميزات", "show_in_filter": True, "sort_order": 1}])
    res = client.get("/dashboard/product-types")
    assert res.status_code == 200
    assert "أنواع المنتجات" in res.text
    assert "سجاد صلاة" in res.text


def test_product_types_page_handles_missing_table(client, authed):
    _, mock_query = authed([])
    mock_query.execute.side_effect = Exception('relation "product_types" does not exist')
    res = client.get("/dashboard/product-types")
    assert res.status_code == 200
    assert "004_product_types.sql" in res.text
    assert "عطور ومسك" in res.text


def test_create_product_type_inserts_row(client, authed):
    _, mock_query = authed([])
    res = client.post("/dashboard/product-types/new", data={
        "name_ar": " مسابح ", "visual": "beads", "size_label": "عدد الحبات", "size_unit": "حبة",
        "details_label": "المميزات",
    }, follow_redirects=False)
    assert res.headers["location"] == "/dashboard/product-types?msg=created"
    inserted = mock_query.insert.call_args[0][0]
    assert inserted["name_ar"] == "مسابح"
    assert inserted["visual"] == "beads"
    assert inserted["store_id"] == STORE_ID


def test_rename_product_type_updates_products(client, authed):
    _, mock_query = authed([{"id": TYPE_ID, "name_ar": "سجاد", "visual": "rug"}])
    res = client.post(f"/dashboard/product-types/{TYPE_ID}/edit", data={
        "name_ar": "سجاد صلاة", "visual": "rug", "size_label": "المقاس", "size_unit": "سم",
    }, follow_redirects=False)
    assert res.headers["location"] == "/dashboard/product-types?msg=updated"
    payloads = [c.args[0] for c in mock_query.update.call_args_list]
    assert {"product_type": "سجاد صلاة"} in payloads


def test_delete_product_type_in_use_is_refused(client, authed):
    _, mock_query = authed([{"id": TYPE_ID, "name_ar": "مسابح", "product_type": "مسابح"}])
    res = client.post(f"/dashboard/product-types/{TYPE_ID}/delete", follow_redirects=False)
    assert res.headers["location"] == "/dashboard/product-types?error=in_use"
    mock_query.delete.assert_not_called()


def test_product_form_shows_type_picker(client, authed):
    authed([{"id": TYPE_ID, "name_ar": "مصاحف وكتب", "visual": "book", "size_label": "الحجم",
             "size_unit": "سم", "details_label": "المميزات", "show_in_filter": True}])
    res = client.get("/dashboard/products/new")
    assert res.status_code == 200
    assert 'name="product_type" value="مصاحف وكتب"' in res.text
    assert 'data-size-unit="سم"' in res.text


def test_product_form_without_types_does_not_block_saving(client, authed):
    authed([])
    res = client.get("/dashboard/products/new")
    assert res.status_code == 200
    assert "لا توجد أنواع منتجات بعد" in res.text


def test_create_product_saves_type(client, authed):
    _, mock_query = authed([])
    res = client.post("/dashboard/products/new", data={
        "name_ar": "مسبحة يسر", "price_jod": "7.5", "stock_quantity": "4",
        "category": "رجالي", "product_type": "مسابح", "size_ml": "",
    }, follow_redirects=False)
    assert res.status_code == 303
    inserted = mock_query.insert.call_args[0][0]
    assert inserted["product_type"] == "مسابح"
    assert inserted["size_ml"] is None


def test_create_product_unticked_active_switch_saves_inactive(client, authed):
    _, mock_query = authed([])
    res = client.post("/dashboard/products/new", data={
        "name_ar": "مسبحة", "price_jod": "5", "category": "رجالي", "product_type": "مسابح",
    }, follow_redirects=False)
    assert res.status_code == 303
    assert mock_query.insert.call_args[0][0]["is_active"] is False


@pytest.mark.parametrize("data", [
    {"name_ar": "   ", "price_jod": "5"},
    {"name_ar": "مسبحة", "price_jod": "-1"},
    {"name_ar": "مسبحة", "price_jod": "100000000"},
])
def test_create_product_rejects_invalid_fields(client, authed, data):
    _, mock_query = authed([])
    res = client.post("/dashboard/products/new", data=data, follow_redirects=False)
    assert res.status_code == 400
    assert 'class="alert alert-danger"' in res.text
    mock_query.insert.assert_not_called()


def test_duplicate_product_name_rerenders_form(client, authed):
    _, mock_query = authed([])
    insert_query = MagicMock()
    insert_query.execute.side_effect = Exception(
        "{'code': '23505', 'message': 'duplicate key value violates unique constraint \"uq_products_store_name\"'}"
    )
    mock_query.insert.return_value = insert_query
    res = client.post("/dashboard/products/new", data={
        "name_ar": "مسبحة يسر", "price_jod": "7.5", "category": "رجالي", "product_type": "مسابح",
    }, follow_redirects=False)
    assert res.status_code == 400
    assert "بنفس الاسم" in res.text
    assert 'value="مسبحة يسر"' in res.text


def test_product_bad_id_is_not_found(client, authed):
    _, mock_query = authed([])
    assert client.get("/dashboard/products/not-a-uuid/edit").status_code == 404
    res = client.post("/dashboard/products/not-a-uuid/delete", follow_redirects=False)
    assert res.status_code == 303
    mock_query.delete.assert_not_called()


def test_products_list_shows_saved_message(client, authed):
    authed([])
    assert "تمت إضافة المنتج بنجاح" in client.get("/dashboard/products?msg=created").text


PHOTO_PREFIX = "https://test-project.supabase.co/storage/v1/object/public/product-images/"
PRODUCT_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 64


def test_detect_photo_type_reads_file_signature():
    assert detect_photo_type(JPEG_BYTES) == ("image/jpeg", "jpg")
    assert detect_photo_type(b"\x89PNG\r\n\x1a\n....") == ("image/png", "png")
    assert detect_photo_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ("image/webp", "webp")
    assert detect_photo_type(b"<svg onload=alert(1)>") is None


def test_create_product_uploads_photo(client, authed):
    mock_db, mock_query = authed([])
    res = client.post("/dashboard/products/new", data={
        "name_ar": "مسبحة", "price_jod": "5",
    }, files={"image_file": ("photo.jpg", JPEG_BYTES, "image/jpeg")}, follow_redirects=False)
    assert res.status_code == 303
    mock_db.storage.from_.assert_called_with("product-images")
    path, data, options = mock_db.storage.from_.return_value.upload.call_args[0]
    assert path.startswith(STORE_ID + "/") and path.endswith(".jpg")
    assert data == JPEG_BYTES and options["content-type"] == "image/jpeg"
    assert mock_query.insert.call_args[0][0]["image_url"] == PHOTO_PREFIX + path


def test_create_product_rejects_non_image_upload(client, authed):
    mock_db, mock_query = authed([])
    res = client.post("/dashboard/products/new", data={
        "name_ar": "مسبحة", "price_jod": "5",
    }, files={"image_file": ("photo.jpg", b"not an image", "image/jpeg")}, follow_redirects=False)
    assert res.status_code == 400
    assert "نوع الملف غير مدعوم" in res.text
    mock_db.storage.from_.return_value.upload.assert_not_called()
    mock_query.insert.assert_not_called()


def test_create_product_without_photo_keeps_pasted_link(client, authed):
    # What a browser sends when the file input is left empty
    mock_db, mock_query = authed([])
    body = "".join(
        f'--B\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in [("name_ar", "مسبحة"), ("price_jod", "5"), ("image_url", "https://example.com/a.jpg")]
    ) + (
        '--B\r\nContent-Disposition: form-data; name="image_file"; filename=""\r\n'
        "Content-Type: application/octet-stream\r\n\r\n\r\n--B--\r\n"
    )
    res = client.post(
        "/dashboard/products/new", content=body.encode(),
        headers={"Content-Type": "multipart/form-data; boundary=B"}, follow_redirects=False,
    )
    assert res.status_code == 303
    mock_db.storage.from_.return_value.upload.assert_not_called()
    assert mock_query.insert.call_args[0][0]["image_url"] == "https://example.com/a.jpg"


def test_edit_product_new_photo_replaces_old_one(client, authed):
    old = PHOTO_PREFIX + STORE_ID + "/old.jpg"
    mock_db, _ = authed([{"id": PRODUCT_ID, "store_id": STORE_ID, "image_url": old}])
    res = client.post(f"/dashboard/products/{PRODUCT_ID}/edit", data={
        "name_ar": "مسبحة", "price_jod": "5", "image_url": old,
    }, files={"image_file": ("photo.jpg", JPEG_BYTES, "image/jpeg")}, follow_redirects=False)
    assert res.status_code == 303
    mock_db.storage.from_.return_value.remove.assert_called_once_with([STORE_ID + "/old.jpg"])


def test_edit_product_unchanged_photo_is_kept(client, authed):
    old = PHOTO_PREFIX + STORE_ID + "/old.jpg"
    mock_db, _ = authed([{"id": PRODUCT_ID, "store_id": STORE_ID, "image_url": old}])
    res = client.post(f"/dashboard/products/{PRODUCT_ID}/edit", data={
        "name_ar": "مسبحة", "price_jod": "5", "image_url": old,
    }, follow_redirects=False)
    assert res.status_code == 303
    mock_db.storage.from_.return_value.remove.assert_not_called()


def test_delete_product_removes_uploaded_photo_only(client, authed):
    mock_db, _ = authed([{"id": PRODUCT_ID, "image_url": PHOTO_PREFIX + STORE_ID + "/a.jpg"}])
    client.post(f"/dashboard/products/{PRODUCT_ID}/delete", follow_redirects=False)
    mock_db.storage.from_.return_value.remove.assert_called_once_with([STORE_ID + "/a.jpg"])

    mock_db, _ = authed([{"id": PRODUCT_ID, "image_url": "https://example.com/a.jpg"}])
    client.post(f"/dashboard/products/{PRODUCT_ID}/delete", follow_redirects=False)
    mock_db.storage.from_.return_value.remove.assert_not_called()


def test_product_save_retries_without_type_before_migration():
    mock_db, mock_query = make_mock_db([{"id": "p1"}])
    mock_query.execute.side_effect = [
        Exception("Could not find the 'product_type' column of 'products'"),
        MagicMock(data=[{"id": "p1"}]),
    ]
    product = ProductCreate(store_id=STORE_ID, name_ar="سجادة", price_jod="10", product_type="سجاد صلاة")
    assert ProductRepository(mock_db).create(STORE_ID, product) == {"id": "p1"}
    retried = mock_query.insert.call_args_list[-1].args[0]
    assert "product_type" not in retried


# ---------------------------------------------------------------------------
# Categories rename / reorder
# ---------------------------------------------------------------------------
def test_rename_category_carries_products(client, authed):
    _, mock_query = authed([{"id": CATEGORY_ID, "name_ar": "رجالي"}])
    res = client.post(f"/dashboard/categories/{CATEGORY_ID}/rename", data={"name_ar": "هدايا رجالية"},
                      follow_redirects=False)
    assert res.headers["location"] == "/dashboard/categories?msg=renamed"
    payloads = [c.args[0] for c in mock_query.update.call_args_list]
    assert {"name_ar": "هدايا رجالية"} in payloads
    assert {"category": "هدايا رجالية"} in payloads


def test_move_category(client, authed):
    authed([{"id": CATEGORY_ID, "name_ar": "رجالي", "sort_order": 1}])
    res = client.post(f"/dashboard/categories/{CATEGORY_ID}/move", data={"direction": "down"},
                      follow_redirects=False)
    assert res.headers["location"] == "/dashboard/categories?msg=reordered"


# ---------------------------------------------------------------------------
# Branding / storefront copy
# ---------------------------------------------------------------------------
def test_build_branding_defaults_and_overrides():
    brand = build_branding({})
    assert brand["store_name"] == "متجر التقوى"
    assert brand["full_name"] == "متجر التقوى لبضائع وهدايا الحج والعمرة"
    assert len(brand["trust_badges"]) == 4
    assert brand["initial"] == "ت"

    brand = build_branding({"store_name": "", "sf_header_seal": "", "sf_trust_badges": "أ\n\nب"})
    assert brand["store_name"] == "متجر التقوى"  # required: empty falls back
    assert brand["sf_header_seal"] == ""  # optional: empty hides it
    assert [b["text"] for b in brand["trust_badges"]] == ["أ", "ب"]


def test_get_branding_caches_until_invalidated():
    mock_db, mock_query = make_mock_db([{"setting_key": "store_name", "setting_value": "متجر النور"}])
    invalidate_branding()
    assert get_branding(mock_db, "store-x")["store_name"] == "متجر النور"
    mock_query.execute.return_value = MagicMock(data=[{"setting_key": "store_name", "setting_value": "تغير"}])
    assert get_branding(mock_db, "store-x")["store_name"] == "متجر النور"
    invalidate_branding("store-x")
    assert get_branding(mock_db, "store-x")["store_name"] == "تغير"
    invalidate_branding()


def test_settings_save_storefront_copy(client, authed):
    _, mock_query = authed([])
    res = client.post("/dashboard/settings", data={
        "store_name": "متجر التقوى", "bot_greeting": "هلا", "bot_tone": "أردني",
        "human_handoff_message": "ثواني", "sf_hero_title_gold": "هدايا الحج",
        "sf_trust_badges": "شحن سريع\nجودة",
    }, follow_redirects=False)
    assert res.status_code == 303
    saved = {c.args[0]["setting_key"]: c.args[0]["setting_value"] for c in mock_query.upsert.call_args_list}
    assert saved["sf_hero_title_gold"] == "هدايا الحج"
    assert saved["sf_trust_badges"] == "شحن سريع\nجودة"
    assert "sf_footer_about" not in saved  # not submitted -> untouched


def test_dashboard_shows_store_name_from_settings(client, authed):
    authed([{"setting_key": "store_name", "setting_value": "متجر النور"}])
    res = client.get("/dashboard/settings")
    assert res.status_code == 200
    assert "متجر النور" in res.text


# ---------------------------------------------------------------------------
# Storefront
# ---------------------------------------------------------------------------
def test_storefront_shows_type_filter_and_no_prices(client):
    res = client.get("/")
    assert res.status_code == 200
    assert 'data-filter-group="type"' in res.text
    assert "سجاد صلاة" in res.text
    assert "د.أ" not in res.text


def test_storefront_type_filter_param(client):
    res = client.get("/partials/products", params={"type": "عطور ومسك"})
    assert res.status_code == 200
    assert "النوع:" in res.text
