"""
Dashboard overview route (recent orders and quick actions).
"""

from typing import Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.orders import OrderRepository
import logging
from app.dependencies import get_config, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard_overview"])


@router.get("", response_class=HTMLResponse)
def show_dashboard_overview(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Render dashboard overview page with the latest orders."""
    store_id = user.get("store_id") or config.default_store_id

    recent_orders = []
    db_warning = None

    try:
        recent_orders = OrderRepository(db).list_by_store(store_id, limit=5)
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
            "active_page": "overview",
            "db_warning": db_warning,
        },
    )
