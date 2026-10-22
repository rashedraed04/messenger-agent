"""
Dashboard products CRUD routes.
"""

from decimal import Decimal
from typing import Any
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.dashboard.pagination import page_offset, paginate
from app.db.repositories.categories import CategoryRepository
from app.db.repositories.product_types import VISUAL_ICONS, ProductTypeRepository
from app.db.repositories.products import ProductRepository
from app.dependencies import get_config, get_db
from app.models.product import ProductCreate, ProductUpdate

router = APIRouter(prefix="/dashboard/products", tags=["dashboard_products"])


@router.get("", response_class=HTMLResponse)
def list_products(
    request: Request,
    q: str | None = Query(None),
    category: str | None = Query(None),
    product_type: str | None = Query(None),
    page: int = Query(1),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """List products with search and category filters."""
    store_id = user.get("store_id") or config.default_store_id
    product_repo = ProductRepository(db)

    page, offset, limit = page_offset(page)
    rows = product_repo.list_by_store(
        store_id=store_id,
        search_query=q,
        category=category or None,
        limit=limit,
        offset=offset,
        product_type=product_type or None,
    )
    products, pagination = paginate(request, rows, page)
    categories = CategoryRepository(db).get_names(store_id)
    types, _ = ProductTypeRepository(db).list_or_default(store_id)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/products/list.html",
        {
            "request": request,
            "user": user,
            "products": products,
            "pagination": pagination,
            "categories": categories,
            "search_query": q or "",
            "selected_category": category or "",
            "product_types": types,
            "selected_type": product_type or "",
            "active_page": "products",
        },
    )


@router.get("/new", response_class=HTMLResponse)
def show_create_product_form(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Render product creation form."""
    store_id = user.get("store_id") or config.default_store_id
    categories = CategoryRepository(db).get_names(store_id)
    types, _ = ProductTypeRepository(db).list_or_default(store_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/products/form.html",
        {
            "request": request,
            "user": user,
            "product": None,
            "categories": categories,
            "product_types": types,
            "type_icons": VISUAL_ICONS,
            "is_edit": False,
            "active_page": "products",
        },
    )


@router.post("/new")
def handle_create_product(
    name_ar: str = Form(...),
    price_jod: float = Form(...),
    name_en: str | None = Form(None),
    brand: str | None = Form(None),
    size_ml: str | None = Form(None),
    category: str | None = Form(None),
    product_type: str | None = Form(None),
    description_ar: str | None = Form(None),
    image_url: str | None = Form(None),
    tags: str | None = Form(None),
    is_active: bool = Form(True),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Create a new product."""
    store_id = user.get("store_id") or config.default_store_id
    product_repo = ProductRepository(db)

    product_create = ProductCreate(
        store_id=store_id,
        name_ar=name_ar,
        name_en=name_en,
        brand=brand,
        size_ml=(size_ml or "").strip() or None,
        price_jod=Decimal(str(price_jod)),
        is_active=is_active,
        category=(category or "").strip() or None,
        product_type=(product_type or "").strip() or None,
        description_ar=description_ar,
        image_url=image_url,
        tags=tags,
    )
    product_repo.create(store_id, product_create)

    return RedirectResponse(
        url="/dashboard/products?msg=created",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{product_id}/edit", response_class=HTMLResponse)
def show_edit_product_form(
    product_id: str,
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Render product edit form."""
    store_id = user.get("store_id") or config.default_store_id
    product_repo = ProductRepository(db)
    product = product_repo.get_by_id(store_id, product_id)

    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    categories = CategoryRepository(db).get_names(store_id)
    types, _ = ProductTypeRepository(db).list_or_default(store_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/products/form.html",
        {
            "request": request,
            "user": user,
            "product": product,
            "categories": categories,
            "product_types": types,
            "type_icons": VISUAL_ICONS,
            "is_edit": True,
            "active_page": "products",
        },
    )


@router.post("/{product_id}/edit")
def handle_edit_product(
    product_id: str,
    name_ar: str = Form(...),
    price_jod: float = Form(...),
    name_en: str | None = Form(None),
    brand: str | None = Form(None),
    size_ml: str | None = Form(None),
    category: str | None = Form(None),
    product_type: str | None = Form(None),
    description_ar: str | None = Form(None),
    image_url: str | None = Form(None),
    tags: str | None = Form(None),
    is_active: bool = Form(False),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Update existing product."""
    store_id = user.get("store_id") or config.default_store_id
    product_repo = ProductRepository(db)

    updates = ProductUpdate(
        name_ar=name_ar,
        name_en=name_en,
        brand=brand,
        size_ml=(size_ml or "").strip() or None,
        price_jod=Decimal(str(price_jod)),
        is_active=is_active,
        category=(category or "").strip() or None,
        product_type=(product_type or "").strip() or None,
        description_ar=description_ar,
        image_url=image_url,
        tags=tags,
    )
    product_repo.update(store_id, product_id, updates)

    return RedirectResponse(
        url="/dashboard/products?msg=updated",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{product_id}/delete")
def handle_delete_product(
    product_id: str,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Delete a product."""
    store_id = user.get("store_id") or config.default_store_id
    product_repo = ProductRepository(db)
    product_repo.delete(store_id, product_id)

    return RedirectResponse(
        url="/dashboard/products?msg=deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )
