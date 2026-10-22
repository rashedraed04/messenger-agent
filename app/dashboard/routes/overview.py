"""
Dashboard overview route (recent orders and quick actions).
"""

from typing import Any
from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.orders import OrderRepository
from app.db.repositories.settings import StoreSettingRepository
import logging
from app.dependencies import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard_overview"])


@router.get("", response_class=HTMLResponse)
def show_dashboard_overview(
    request: Request,
    msg: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Render dashboard overview page with the latest orders."""
    store_id = user.get("store_id") or config.default_store_id

    recent_orders = []
    bot_enabled = True
    db_warning = None

    try:
        recent_orders = OrderRepository(db).list_by_store(store_id, limit=5)
        bot_enabled = StoreSettingRepository(db).get_bot_config(store_id).get("bot_enabled", True)
    except Exception as e:
        logger.warning("Could not fetch recent orders: %s", e)
        db_warning = "تعذر تحميل بعض البيانات المحدثة من قاعدة البيانات."

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "user": user,
            "recent_orders": recent_orders,
            "bot_enabled": bot_enabled,
            "msg": msg,
            "active_page": "overview",
            "db_warning": db_warning,
        },
    )


@router.post("/bot-toggle")
def toggle_bot(
    enabled: bool = Form(False),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Quick switch for the Messenger bot from the overview page."""
    store_id = user.get("store_id") or config.default_store_id
    StoreSettingRepository(db).set_value(store_id, "bot_enabled", "true" if enabled else "false", "boolean")
    return RedirectResponse(
        url=f"/dashboard?msg={'bot_on' if enabled else 'bot_off'}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
