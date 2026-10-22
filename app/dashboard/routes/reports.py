"""
Dashboard daily reports management and manual dispatch routes.
"""

from typing import Any
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.orders import OrderRepository
from app.db.repositories.reports import ReportRepository
from app.db.repositories.settings import StoreSettingRepository
from app.dependencies import get_config, get_db
from app.services.report_service import ReportService
from app.telegram.reporter import TelegramReporter

router = APIRouter(prefix="/dashboard/reports", tags=["dashboard_reports"])


@router.get("", response_class=HTMLResponse)
def list_reports(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """List historical daily Telegram reports."""
    store_id = user.get("store_id") or config.default_store_id
    report_repo = ReportRepository(db)
    reports = report_repo.list_history(store_id, limit=30)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        "dashboard/reports/list.html",
        {
            "request": request,
            "user": user,
            "reports": reports,
            "active_page": "reports",
        },
    )


@router.post("/send-now")
async def trigger_manual_report(
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Manually generate and send today's Telegram report."""
    store_id = user.get("store_id") or config.default_store_id

    order_repo = OrderRepository(db)
    report_repo = ReportRepository(db)
    setting_repo = StoreSettingRepository(db)
    telegram_reporter = TelegramReporter(
        bot_token=config.telegram_bot_token,
        chat_id=config.telegram_chat_id,
    )

    report_service = ReportService(
        order_repo=order_repo,
        report_repo=report_repo,
        setting_repo=setting_repo,
        telegram_reporter=telegram_reporter,
    )

    await report_service.generate_and_send_daily_report(store_id=store_id, force_resend=True)

    return RedirectResponse(
        url="/dashboard/reports?msg=report_dispatched",
        status_code=status.HTTP_303_SEE_OTHER,
    )
