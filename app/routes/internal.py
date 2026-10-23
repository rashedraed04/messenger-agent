"""
Internal API endpoints.

Secured by the X-Internal-Token header (sent by the cron-job.org job).
These endpoints are NOT for external use.
"""

import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from supabase import Client

from app.config import Settings
from app.db.repositories.notification_settings import NotificationSettingRepository
from app.db.repositories.orders import OrderRepository
from app.db.repositories.reports import ReportRepository
from app.db.repositories.settings import StoreSettingRepository
from app.dependencies import get_config, get_db
from app.services.report_service import ReportService
from app.telegram.reporter import TelegramReporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def verify_internal_token(
    x_internal_token: str = Header(...),
    config: Settings = Depends(get_config),
) -> None:
    """Verify the internal API token sent by the scheduler; refuse everything if unset."""
    if not config.internal_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal API not configured",
        )
    if not hmac.compare_digest(x_internal_token.encode(), config.internal_api_token.encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid internal token",
        )


@router.post("/daily-report", status_code=status.HTTP_200_OK)
async def trigger_daily_report(
    force: bool = Query(False, description="Force resend if already sent"),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
    _: None = Depends(verify_internal_token),
) -> dict:
    """
    Trigger the daily order report.

    Called by cron-job.org at 21:00 Asia/Amman.
    Also serves as a daily DB ping to prevent Supabase free-tier auto-pause.
    """
    store_id = config.default_store_id

    # This lookup still pings the DB, so the keepalive works while reports are off
    if not force and not NotificationSettingRepository(db).should_send_daily_report(store_id):
        logger.info("Daily report is turned off for store %s. Skipping.", store_id)
        return {
            "status": "skipped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "store_id": store_id,
            "reason": "daily_report_disabled",
        }

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

    try:
        result = await report_service.generate_and_send_daily_report(
            store_id=store_id,
            force_resend=force,
            scheduled=True,
        )
        return {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **result,
        }
    except Exception as e:
        logger.exception("Daily report generation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Report failed; see server logs",
        )
