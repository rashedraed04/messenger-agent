"""
Dashboard guided setup checklist route.
"""

from typing import Any
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.dependencies import get_config, get_db

router = APIRouter(prefix="/dashboard/setup", tags=["dashboard_setup"])


@router.get("", response_class=HTMLResponse)
def show_setup_checklist(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Render guided step-by-step setup checklist with status indicators."""
    store_id = user.get("store_id") or config.default_store_id

    product_repo = ProductRepository(db)
    setting_repo = StoreSettingRepository(db)

    products = product_repo.list_by_store(store_id, limit=5)
    delivery_fee_set = bool(setting_repo.get_value(store_id, "delivery_fee_jod"))

    # Status check items
    checklist = [
        {
            "id": "db",
            "title": "قاعدة البيانات Supabase",
            "description": "الاتصال بقاعدة بيانات PostgreSQL وجداول النظام الـ 12",
            "status": "completed" if db else "pending",
            "action_url": None,
            "action_label": None,
        },
        {
            "id": "products",
            "title": "إضافة المنتجات والأسعار",
            "description": f"تمت إضافة {len(products)} منتجات (الحد الأدنى المقترح 10 منتجات)",
            "status": "completed" if len(products) >= 1 else "pending",
            "action_url": "/dashboard/products/new",
            "action_label": "إضافة منتج",
        },
        {
            "id": "delivery_fee",
            "title": "رسوم شركة التوصيل",
            "description": "رسوم توصيل ثابتة لكل المحافظات تضاف إلى مجموع الطلب",
            "status": "completed" if delivery_fee_set else "pending",
            "action_url": "/dashboard/settings",
            "action_label": "تحديد الرسوم",
        },
        {
            "id": "gemini",
            "title": "مفتاح الذكاء الاصطناعي (Gemini API)",
            "description": "مزود الذكاء الاصطناعي للمحادثات باللهجة الأردنية",
            "status": "completed" if config.gemini_api_key else "pending",
            "action_url": "/dashboard/settings",
            "action_label": "فحص المفتاح",
        },
        {
            "id": "meta",
            "title": "ربط صفحة الفيسبوك (Meta Webhook)",
            "description": f"رابط الويب هوك: {request.base_url}webhook",
            "status": "completed" if (config.meta_page_access_token and config.meta_app_secret) else "pending",
            "action_url": "/dashboard/settings",
            "action_label": "تعليمات الربط",
        },
        {
            "id": "telegram",
            "title": "بوت التيليجرام للتقارير اليومية",
            "description": "إرسال قائمة طلبيات اليوم كل ليلة الساعة 10:00 مساءً لتسليمها لشركة التوصيل",
            "status": "completed" if (config.telegram_bot_token and config.telegram_chat_id) else "pending",
            "action_url": "/dashboard/reports",
            "action_label": "فحص التقرير",
        },
    ]

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/setup.html",
        {
            "request": request,
            "user": user,
            "checklist": checklist,
            "active_page": "setup",
        },
    )
