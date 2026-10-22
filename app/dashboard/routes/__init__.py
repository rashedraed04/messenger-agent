"""
Dashboard routes package.
"""

from fastapi import APIRouter

from app.dashboard.routes.account import router as account_router
from app.dashboard.routes.agent_chat import router as agent_chat_router
from app.dashboard.routes.auth import router as auth_router
from app.dashboard.routes.categories import router as categories_router
from app.dashboard.routes.faqs import router as faqs_router
from app.dashboard.routes.overview import router as overview_router
from app.dashboard.routes.product_types import router as product_types_router
from app.dashboard.routes.products import router as products_router
from app.dashboard.routes.reports import router as reports_router
from app.dashboard.routes.settings import router as settings_router
from app.dashboard.routes.setup import router as setup_router

# Unified dashboard router
dashboard_router = APIRouter()
dashboard_router.include_router(overview_router)
dashboard_router.include_router(products_router)
dashboard_router.include_router(categories_router)
dashboard_router.include_router(product_types_router)
dashboard_router.include_router(agent_chat_router)
dashboard_router.include_router(faqs_router)
dashboard_router.include_router(reports_router)
dashboard_router.include_router(settings_router)
dashboard_router.include_router(setup_router)
dashboard_router.include_router(account_router)

__all__ = ["auth_router", "dashboard_router"]
