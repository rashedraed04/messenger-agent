"""
Dashboard products CRUD routes.
"""

import math
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
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
from app.services.product_photos import MAX_UPLOAD_BYTES, PhotoError, delete_photo, upload_photo

router = APIRouter(prefix="/dashboard/products", tags=["dashboard_products"])

# products.price_jod is NUMERIC(10,3)
MAX_PRICE_JOD = 9_999_999.999
DUPLICATE_NAME_ERROR = "يوجد منتج آخر بنفس الاسم العربي. اختر اسماً مختلفاً."


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _is_duplicate_name(error: Exception) -> bool:
    """products has UNIQUE (store_id, name_ar); Postgres reports it as 23505."""
    text = str(error)
    return "23505" in text or "uq_products_store_name" in text or "duplicate key" in text


def _clean_fields(
    name_ar: str,
    price_jod: float,
    name_en: str | None,
    brand: str | None,
    size_ml: str | None,
    category: str | None,
    product_type: str | None,
    description_ar: str | None,
    image_url: str | None,
    tags: str | None,
    is_active: bool,
) -> dict[str, Any]:
    """Trim submitted fields; blank optional fields become None."""

    def clean(value: str | None) -> str | None:
        return (value or "").strip() or None

    return {
        "name_ar": " ".join((name_ar or "").split()),
        "name_en": clean(name_en),
        "brand": clean(brand),
        "size_ml": clean(size_ml),
        "price_jod": price_jod,
        "is_active": is_active,
        "category": clean(category),
        "product_type": clean(product_type),
        "description_ar": clean(description_ar),
        "image_url": clean(image_url),
        "tags": clean(tags),
    }


def _validation_error(fields: dict[str, Any]) -> str | None:
    if not fields["name_ar"]:
        return "اسم المنتج بالعربي مطلوب."
    price = fields["price_jod"]
    if not math.isfinite(price) or price < 0 or price > MAX_PRICE_JOD:
        return "السعر غير صالح."
    return None


def _attach_photo(
    db: Client,
    config: Settings,
    store_id: str,
    fields: dict[str, Any],
    image_file: UploadFile | None,
) -> str | None:
    """Upload a chosen photo and point image_url at it; returns an error message on failure."""
    # A file input left empty is still submitted, with no filename
    if not image_file or not image_file.filename:
        return None
    try:
        fields["image_url"] = upload_photo(
            db, config.supabase_url, store_id, image_file.file.read(MAX_UPLOAD_BYTES + 1)
        )
    except PhotoError as e:
        return str(e)
    return None


def _render_form(
    request: Request,
    user: dict[str, Any],
    db: Client,
    store_id: str,
    product: dict[str, Any] | None,
    is_edit: bool,
    error: str | None = None,
):
    """Render the product form; on error it is refilled with what was submitted."""
    categories = CategoryRepository(db).get_names(store_id)
    types, _ = ProductTypeRepository(db).list_or_default(store_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/products/form.html",
        {
            "request": request,
            "user": user,
            "product": product,
            "categories": categories,
            "product_types": types,
            "type_icons": VISUAL_ICONS,
            "is_edit": is_edit,
            "error": error,
            "active_page": "products",
        },
        status_code=status.HTTP_400_BAD_REQUEST if error else status.HTTP_200_OK,
    )


@router.get("", response_class=HTMLResponse)
def list_products(
    request: Request,
    q: str | None = Query(None),
    category: str | None = Query(None),
    product_type: str | None = Query(None),
    page: int = Query(1),
    msg: str | None = Query(None),
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
        request,
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
            "msg": msg,
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
    return _render_form(request, user, db, store_id, None, is_edit=False)


@router.post("/new")
def handle_create_product(
    request: Request,
    name_ar: str = Form(...),
    price_jod: float = Form(...),
    name_en: str | None = Form(None),
    brand: str | None = Form(None),
    size_ml: str | None = Form(None),
    category: str | None = Form(None),
    product_type: str | None = Form(None),
    description_ar: str | None = Form(None),
    image_url: str | None = Form(None),
    image_file: UploadFile | None = File(None),
    tags: str | None = Form(None),
    # An unticked checkbox is not submitted at all, so absent means inactive
    is_active: bool = Form(False),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Create a new product."""
    store_id = user.get("store_id") or config.default_store_id
    fields = _clean_fields(
        name_ar, price_jod, name_en, brand, size_ml, category,
        product_type, description_ar, image_url, tags, is_active,
    )
    error = _validation_error(fields)
    if error:
        return _render_form(request, user, db, store_id, fields, is_edit=False, error=error)
    submitted_image = fields["image_url"]
    error = _attach_photo(db, config, store_id, fields, image_file)
    if error:
        return _render_form(request, user, db, store_id, fields, is_edit=False, error=error)

    product_create = ProductCreate(
        store_id=store_id, **{**fields, "price_jod": Decimal(str(price_jod))}
    )
    try:
        ProductRepository(db).create(store_id, product_create)
    except Exception as e:
        if fields["image_url"] != submitted_image:
            delete_photo(db, config.supabase_url, fields["image_url"])
        if not _is_duplicate_name(e):
            raise
        fields["image_url"] = submitted_image
        return _render_form(
            request, user, db, store_id, fields, is_edit=False, error=DUPLICATE_NAME_ERROR
        )

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
    product = ProductRepository(db).get_by_id(store_id, product_id) if _is_uuid(product_id) else None
    if not product:
        raise HTTPException(status_code=404, detail="المنتج غير موجود")

    return _render_form(request, user, db, store_id, product, is_edit=True)


@router.post("/{product_id}/edit")
def handle_edit_product(
    product_id: str,
    request: Request,
    name_ar: str = Form(...),
    price_jod: float = Form(...),
    name_en: str | None = Form(None),
    brand: str | None = Form(None),
    size_ml: str | None = Form(None),
    category: str | None = Form(None),
    product_type: str | None = Form(None),
    description_ar: str | None = Form(None),
    image_url: str | None = Form(None),
    image_file: UploadFile | None = File(None),
    tags: str | None = Form(None),
    is_active: bool = Form(False),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Update existing product."""
    store_id = user.get("store_id") or config.default_store_id
    if not _is_uuid(product_id):
        raise HTTPException(status_code=404, detail="المنتج غير موجود")
    product_repo = ProductRepository(db)

    fields = _clean_fields(
        name_ar, price_jod, name_en, brand, size_ml, category,
        product_type, description_ar, image_url, tags, is_active,
    )
    submitted = {**fields, "id": product_id}
    error = _validation_error(fields)
    if error:
        return _render_form(request, user, db, store_id, submitted, is_edit=True, error=error)
    existing = product_repo.get_by_id(store_id, product_id) or {}
    error = _attach_photo(db, config, store_id, fields, image_file)
    if error:
        return _render_form(request, user, db, store_id, submitted, is_edit=True, error=error)

    updates = ProductUpdate(**{**fields, "price_jod": Decimal(str(price_jod))})
    try:
        product_repo.update(store_id, product_id, updates)
    except Exception as e:
        if fields["image_url"] != submitted["image_url"]:
            delete_photo(db, config.supabase_url, fields["image_url"])
        if not _is_duplicate_name(e):
            raise
        return _render_form(
            request, user, db, store_id, submitted, is_edit=True, error=DUPLICATE_NAME_ERROR
        )

    # The old photo is no longer used once it was replaced or removed
    if existing.get("image_url") != fields["image_url"]:
        delete_photo(db, config.supabase_url, existing.get("image_url"))

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
    product = product_repo.get_by_id(store_id, product_id) if _is_uuid(product_id) else None
    if product and product_repo.delete(store_id, product_id):
        delete_photo(db, config.supabase_url, product.get("image_url"))

    return RedirectResponse(
        url="/dashboard/products?msg=deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )
