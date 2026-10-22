"""
Dashboard product types management routes.
"""

import logging
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.product_types import (
    MAX_LABEL_LENGTH,
    MAX_TYPE_NAME_LENGTH,
    VISUAL_ICONS,
    VISUALS,
    ProductTypeRepository,
    ProductTypeUnavailableError,
    clean_type_fields,
)
from app.dependencies import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/product-types", tags=["dashboard_product_types"])

LIST_URL = "/dashboard/product-types"


def _redirect(query: str) -> RedirectResponse:
    return RedirectResponse(url=f"{LIST_URL}?{query}", status_code=status.HTTP_303_SEE_OTHER)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


@router.get("", response_class=HTMLResponse)
def list_product_types(
    request: Request,
    msg: str | None = Query(None),
    error: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """List product types with product counts and storefront filter visibility."""
    store_id = user.get("store_id") or config.default_store_id
    type_repo = ProductTypeRepository(db)
    types, table_ready = type_repo.list_or_default(store_id)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/product_types/list.html",
        {
            "request": request,
            "user": user,
            "types": types,
            "product_counts": type_repo.count_products(store_id) if table_ready else {},
            "table_ready": table_ready,
            "visuals": VISUALS,
            "type_icons": VISUAL_ICONS,
            "max_name_length": MAX_TYPE_NAME_LENGTH,
            "max_label_length": MAX_LABEL_LENGTH,
            "msg": msg,
            "error": error,
            "active_page": "product_types",
        },
    )


@router.post("/new")
def handle_create_product_type(
    name_ar: str = Form(...),
    visual: str = Form("gift"),
    size_label: str | None = Form(None),
    size_unit: str | None = Form(None),
    details_label: str | None = Form(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Add a new product type."""
    store_id = user.get("store_id") or config.default_store_id
    type_repo = ProductTypeRepository(db)

    fields = clean_type_fields(name_ar, visual, size_label, size_unit, details_label)
    if not fields:
        return _redirect("error=invalid_name")

    try:
        if type_repo.exists(store_id, fields["name_ar"]):
            return _redirect("error=duplicate")
        type_repo.create(store_id, fields)
    except ProductTypeUnavailableError:
        return _redirect("error=not_ready")

    return _redirect("msg=created")


@router.post("/{type_id}/edit")
def handle_edit_product_type(
    type_id: str,
    name_ar: str = Form(...),
    visual: str = Form("gift"),
    size_label: str | None = Form(None),
    size_unit: str | None = Form(None),
    details_label: str | None = Form(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Update a product type; a rename follows through to its products."""
    store_id = user.get("store_id") or config.default_store_id
    type_repo = ProductTypeRepository(db)
    if not _is_uuid(type_id):
        return _redirect("error=not_found")

    fields = clean_type_fields(name_ar, visual, size_label, size_unit, details_label)
    if not fields:
        return _redirect("error=invalid_name")

    try:
        ptype = type_repo.get_by_id(store_id, type_id)
        if not ptype:
            return _redirect("error=not_found")
        if type_repo.exists(store_id, fields["name_ar"], exclude_id=type_id):
            return _redirect("error=duplicate")
    except ProductTypeUnavailableError:
        return _redirect("error=not_ready")

    type_repo.update(store_id, type_id, fields, old_name=ptype["name_ar"])
    return _redirect("msg=updated")


@router.post("/{type_id}/visibility")
def handle_toggle_type_visibility(
    type_id: str,
    show_in_filter: bool = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Show or hide a type in the public storefront filter."""
    store_id = user.get("store_id") or config.default_store_id
    type_repo = ProductTypeRepository(db)
    if not _is_uuid(type_id):
        return _redirect("error=not_found")

    try:
        if not type_repo.get_by_id(store_id, type_id):
            return _redirect("error=not_found")
    except ProductTypeUnavailableError:
        return _redirect("error=not_ready")

    type_repo.set_filter_visibility(store_id, type_id, show_in_filter)
    return _redirect("msg=updated")


@router.post("/{type_id}/move")
def handle_move_product_type(
    type_id: str,
    direction: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Move a type up or down in the display order."""
    store_id = user.get("store_id") or config.default_store_id
    if not _is_uuid(type_id):
        return _redirect("error=not_found")
    try:
        ProductTypeRepository(db).move(store_id, type_id, -1 if direction == "up" else 1)
    except ProductTypeUnavailableError:
        return _redirect("error=not_ready")
    return _redirect("msg=reordered")


@router.post("/{type_id}/delete")
def handle_delete_product_type(
    type_id: str,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Delete a product type; refused while products still use it."""
    store_id = user.get("store_id") or config.default_store_id
    type_repo = ProductTypeRepository(db)
    if not _is_uuid(type_id):
        return _redirect("error=not_found")

    try:
        ptype = type_repo.get_by_id(store_id, type_id)
    except ProductTypeUnavailableError:
        return _redirect("error=not_ready")
    if not ptype:
        return _redirect("error=not_found")

    if type_repo.count_products(store_id).get(ptype["name_ar"], 0) > 0:
        return _redirect("error=in_use")

    type_repo.delete(store_id, type_id)
    return _redirect("msg=deleted")
