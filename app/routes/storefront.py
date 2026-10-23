"""
Public storefront routes for customers to browse available products
(Hajj & Umrah goods and gifts).

CRITICAL POLICY:
Prices are strictly omitted from all public pages and API responses.
Customers query prices or order by clicking "Order via Messenger / Inquire Price".
"""

from typing import Any
from urllib.parse import quote
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from supabase import Client

from app.config import Settings
from app.db.repositories.categories import CategoryRepository
from app.db.repositories.product_types import (
    VISUAL_ICONS,
    ProductTypeRepository,
    describe_product,
    format_size,
)
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.dependencies import get_config, get_db

router = APIRouter(tags=["storefront"])

ALL_CATEGORIES = "الكل"
RELATED_PRODUCTS_LIMIT = 4


DEFAULT_STORE_NAME = "متجر التقوى"
DEFAULT_STORE_DESC = "بضائع وهدايا الحج والعمرة بجودة مضمونة مع توصيل سريع لجميع المحافظات والدفع عند الاستلام كاش"


def _store_info(db: Client, store_id: str) -> tuple[str, str]:
    """Return (store_name, store_desc) from settings or defaults."""
    try:
        bot_config = StoreSettingRepository(db).get_bot_config(store_id)
        store_name = bot_config.get("store_name") or DEFAULT_STORE_NAME
        store_desc = bot_config.get("store_description") or DEFAULT_STORE_DESC
    except Exception:
        store_name = DEFAULT_STORE_NAME
        store_desc = DEFAULT_STORE_DESC
    return store_name, store_desc


def _page_id(config: Settings) -> str:
    return config.facebook_page_id or "perfumestore.jo"


def _decorate(
    products: list[dict[str, Any]], types_by_name: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach display info from the product's type: illustration, size text, details label."""
    for p in products:
        info = describe_product(p, types_by_name)
        p["visual"] = info["visual"]
        p["size_text"] = format_size(p, info)
        p["details_label"] = info["details_label"] or "المميزات"
    return products


def _add_messenger_links(products: list[dict[str, Any]], page_id: str) -> list[dict[str, Any]]:
    """Pre-generate the Messenger inquiry link for each product."""
    for p in products:
        brand = f" ({p['brand']})" if p.get("brand") else ""
        msg_text = f"مرحبا، حابب أستفسر عن سعر وتوفر {p.get('name_ar')}{brand}"
        p["messenger_url"] = f"https://m.me/{page_id}?text={quote(msg_text)}"
    return products


def _clean_category(category: str | None) -> str | None:
    """Treat 'الكل' or empty as no category filter."""
    return category if category and category != ALL_CATEGORIES else None


def _catalog_context(
    db: Client,
    config: Settings,
    q: str | None,
    category: str | None,
    product_type: str | None = None,
    types_by_name: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Products and filter state shared by the full page and the live-search partial."""
    store_id = config.default_store_id
    if types_by_name is None:
        types_by_name = ProductTypeRepository(db).by_name(store_id)
    # Retrieve products with prices strictly stripped
    products = ProductRepository(db).get_public_showcase(
        store_id=store_id,
        search_query=q,
        category=_clean_category(category),
        product_type=_clean_category(product_type),
    )
    _decorate(products, types_by_name)
    _add_messenger_links(products, _page_id(config))
    return {
        "products": products,
        "search_query": q or "",
        "selected_category": category or ALL_CATEGORIES,
        "selected_type": _clean_category(product_type) or "",
        "total_count": len(products),
    }


@router.get("/", response_class=HTMLResponse)
def show_storefront(
    request: Request,
    q: str | None = Query(None, description="Search term for products"),
    category: str | None = Query(None, description="Category filter"),
    product_type: str | None = Query(None, alias="type", description="Product type filter"),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """
    Public customer showcase displaying active, in-stock products.
    CRITICAL: Never exposes price_jod.
    """
    store_id = config.default_store_id
    store_name, store_desc = _store_info(db, store_id)
    categories = CategoryRepository(db).get_names(store_id, only_filter_visible=True)
    types, _ = ProductTypeRepository(db).list_or_default(store_id)
    types_by_name = {t["name_ar"]: t for t in types}
    type_filters = [
        {"name": t["name_ar"], "icon": VISUAL_ICONS.get(t.get("visual"), "bi-gift")}
        for t in types if t.get("show_in_filter")
    ]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "storefront/index.html",
        {
            "request": request,
            **_catalog_context(db, config, q, category, product_type, types_by_name),
            "categories": categories,
            "type_filters": type_filters,
            "store_name": store_name,
            "store_desc": store_desc,
            "facebook_page_id": _page_id(config),
        },
    )


@router.get("/partials/products", response_class=HTMLResponse)
def storefront_results_partial(
    request: Request,
    q: str | None = Query(None),
    category: str | None = Query(None),
    product_type: str | None = Query(None, alias="type"),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """HTML fragment of the results grid used by live search (no page reload)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "storefront/_results.html",
        {"request": request, **_catalog_context(db, config, q, category, product_type)},
    )


@router.get("/perfume/{product_id}", response_class=HTMLResponse)
def show_product_detail(
    product_id: str,
    request: Request,
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Public product page: notes, size, category and Messenger CTA. Never shows price."""
    store_id = config.default_store_id
    product_repo = ProductRepository(db)

    templates = request.app.state.templates
    product = product_repo.get_public_by_id(store_id, product_id)
    store_name, store_desc = _store_info(db, store_id)
    page_id = _page_id(config)

    if not product:
        return templates.TemplateResponse(
            request,
            "storefront/not_found.html",
            {
                "request": request,
                "store_name": store_name,
                "store_desc": store_desc,
                "facebook_page_id": page_id,
            },
            status_code=404,
        )

    types_by_name = ProductTypeRepository(db).by_name(store_id)
    _decorate([product], types_by_name)
    _add_messenger_links([product], page_id)

    # Related: same type first (falls back to same category for untyped products)
    related: list[dict[str, Any]] = []
    if product.get("product_type") or product.get("category"):
        filters = (
            {"product_type": product["product_type"]}
            if product.get("product_type")
            else {"category": product["category"]}
        )
        related = [
            p for p in product_repo.get_public_showcase(store_id, **filters)
            if p.get("id") != product.get("id")
        ][:RELATED_PRODUCTS_LIMIT]
        _decorate(related, types_by_name)
        _add_messenger_links(related, page_id)

    notes = [t.strip() for t in (product.get("tags") or "").split(",") if t.strip()]

    return templates.TemplateResponse(
        request,
        "storefront/detail.html",
        {
            "request": request,
            "product": product,
            "notes": notes,
            "related": related,
            "store_name": store_name,
            "store_desc": store_desc,
            "facebook_page_id": page_id,
        },
    )


@router.get("/privacy", response_class=HTMLResponse)
def show_privacy_policy(
    request: Request,
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Public privacy policy (required by Meta to publish the Messenger app)."""
    store_name, store_desc = _store_info(db, config.default_store_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "storefront/privacy.html",
        {
            "request": request,
            "store_name": store_name,
            "store_desc": store_desc,
            "facebook_page_id": _page_id(config),
        },
    )


@router.get("/api/public/products")
def api_public_products(
    q: str | None = Query(None),
    category: str | None = Query(None),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
) -> dict[str, Any]:
    """
    Public API endpoint returning available products list.
    Guaranteed: NO prices returned.
    """
    store_id = config.default_store_id
    product_repo = ProductRepository(db)

    products = product_repo.get_public_showcase(
        store_id=store_id,
        search_query=q,
        category=_clean_category(category),
    )

    return {
        "status": "success",
        "total": len(products),
        "products": products,
    }
