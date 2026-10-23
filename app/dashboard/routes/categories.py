"""
Dashboard product categories management routes.
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.categories import (
    DEFAULT_CATEGORIES,
    MAX_CATEGORY_NAME_LENGTH,
    CategoryRepository,
    CategoryUnavailableError,
)
from app.dependencies import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/categories", tags=["dashboard_categories"])

LIST_URL = "/dashboard/categories"


def _redirect(query: str) -> RedirectResponse:
    return RedirectResponse(url=f"{LIST_URL}?{query}", status_code=status.HTTP_303_SEE_OTHER)


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


@router.get("", response_class=HTMLResponse)
def list_categories(
    request: Request,
    msg: str | None = Query(None),
    error: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """List categories with product counts and storefront filter visibility."""
    store_id = user.get("store_id") or config.default_store_id
    category_repo = CategoryRepository(db)

    table_ready = True
    try:
        categories = category_repo.list_by_store(store_id)
    except Exception as e:
        logger.warning("product_categories table unavailable: %s", e)
        table_ready = False
        categories = [{"id": None, "name_ar": name, "show_in_filter": True} for name in DEFAULT_CATEGORIES]

    product_counts = category_repo.count_products(store_id)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/categories/list.html",
        {
            "request": request,
            "user": user,
            "categories": categories,
            "product_counts": product_counts,
            "table_ready": table_ready,
            "max_name_length": MAX_CATEGORY_NAME_LENGTH,
            "msg": msg,
            "error": error,
            "active_page": "categories",
        },
    )


@router.post("/new")
def handle_create_category(
    name_ar: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Add a new category."""
    store_id = user.get("store_id") or config.default_store_id
    category_repo = CategoryRepository(db)

    name = " ".join(name_ar.split())
    if not name or len(name) > MAX_CATEGORY_NAME_LENGTH:
        return _redirect("error=invalid_name")

    try:
        if category_repo.exists(store_id, name):
            return _redirect("error=duplicate")
        category_repo.create(store_id, name)
    except CategoryUnavailableError:
        return _redirect("error=not_ready")

    return _redirect("msg=created")


@router.post("/{category_id}/visibility")
def handle_toggle_visibility(
    category_id: str,
    show_in_filter: bool = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Show or hide a category in the public storefront filter."""
    store_id = user.get("store_id") or config.default_store_id
    category_repo = CategoryRepository(db)
    if not _is_uuid(category_id):
        return _redirect("error=not_found")

    try:
        if not category_repo.get_by_id(store_id, category_id):
            return _redirect("error=not_found")
        category_repo.set_filter_visibility(store_id, category_id, show_in_filter)
    except CategoryUnavailableError:
        return _redirect("error=not_ready")

    return _redirect("msg=updated")


@router.post("/{category_id}/rename")
def handle_rename_category(
    category_id: str,
    name_ar: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Rename a category; products using it follow the new name."""
    store_id = user.get("store_id") or config.default_store_id
    category_repo = CategoryRepository(db)
    if not _is_uuid(category_id):
        return _redirect("error=not_found")

    name = " ".join(name_ar.split())
    if not name or len(name) > MAX_CATEGORY_NAME_LENGTH:
        return _redirect("error=invalid_name")

    try:
        category = category_repo.get_by_id(store_id, category_id)
        if not category:
            return _redirect("error=not_found")
        if name == category["name_ar"]:
            return _redirect("msg=updated")
        if category_repo.exists(store_id, name):
            return _redirect("error=duplicate")
    except CategoryUnavailableError:
        return _redirect("error=not_ready")

    category_repo.rename(store_id, category_id, category["name_ar"], name)
    return _redirect("msg=renamed")


@router.post("/{category_id}/move")
def handle_move_category(
    category_id: str,
    direction: str = Form(...),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Move a category up or down in the storefront filter order."""
    store_id = user.get("store_id") or config.default_store_id
    if not _is_uuid(category_id):
        return _redirect("error=not_found")
    try:
        CategoryRepository(db).move(store_id, category_id, -1 if direction == "up" else 1)
    except CategoryUnavailableError:
        return _redirect("error=not_ready")
    return _redirect("msg=reordered")


@router.post("/{category_id}/delete")
def handle_delete_category(
    category_id: str,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Delete a category; refused while products still use it."""
    store_id = user.get("store_id") or config.default_store_id
    category_repo = CategoryRepository(db)
    if not _is_uuid(category_id):
        return _redirect("error=not_found")

    try:
        category = category_repo.get_by_id(store_id, category_id)
    except CategoryUnavailableError:
        return _redirect("error=not_ready")
    if not category:
        return _redirect("error=not_found")

    if category_repo.count_products(store_id).get(category["name_ar"], 0) > 0:
        return _redirect("error=in_use")

    category_repo.delete(store_id, category_id)
    return _redirect("msg=deleted")
