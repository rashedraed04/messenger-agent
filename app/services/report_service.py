"""
Report generation and distribution service.
"""

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any
from dateutil import tz

from app.db.repositories.orders import OrderRepository
from app.db.repositories.reports import ReportRepository
from app.db.repositories.settings import StoreSettingRepository
from app.telegram.reporter import TelegramReporter, format_telegram_daily_report

logger = logging.getLogger(__name__)

AMMAN_TZ = tz.gettz("Asia/Amman") or timezone(timedelta(hours=3))


class ReportService:
    """Manages daily order report aggregation and Telegram delivery."""

    def __init__(
        self,
        order_repo: OrderRepository,
        report_repo: ReportRepository,
        setting_repo: StoreSettingRepository,
        telegram_reporter: TelegramReporter,
    ):
        self.order_repo = order_repo
        self.report_repo = report_repo
        self.setting_repo = setting_repo
        self.telegram_reporter = telegram_reporter

    def get_amman_today(self) -> date:
        """Get current date in Jordan (Asia/Amman)."""
        return datetime.now(AMMAN_TZ).date()

    async def generate_and_send_daily_report(
        self,
        store_id: str,
        target_date: date | None = None,
        force_resend: bool = False,
        scheduled: bool = False,
    ) -> dict[str, Any]:
        """
        Aggregate confirmed orders for target_date and send report via Telegram.
        Also persists result in report_history table for auditing and keepalive.

        Only a successful scheduled (nightly) send blocks a repeat for the day;
        a manual "send now" from the dashboard never stops the nightly report.

        Returns:
            Dict summarizing report result:
            {"store_id": ..., "report_date": ..., "orders_count": ..., "sent": ..., "content": ...}
        """
        if target_date is None:
            target_date = self.get_amman_today()

        existing = self.report_repo.get_by_date(store_id, target_date)
        nightly_already_sent = bool(
            existing and existing.get("sent_successfully") and existing.get("is_scheduled")
        )

        # Check if already sent and not forced
        if not force_resend:
            if nightly_already_sent:
                logger.info(
                    "Report for store %s on %s was already sent successfully. Skipping.",
                    store_id,
                    target_date,
                )
                return {
                    "store_id": store_id,
                    "report_date": target_date.isoformat(),
                    "already_sent": True,
                    "sent": True,
                }

        # 1. Fetch store info
        store_settings = self.setting_repo.get_all(store_id)
        store_name = store_settings.get("store_name", "متجر التقوى")

        # 2. Query confirmed orders for the date (also acts as Supabase keepalive)
        confirmed_orders = self.order_repo.get_confirmed_orders_by_date(store_id, target_date)

        # 3. Format report
        date_str = target_date.strftime("%Y-%m-%d")
        report_text = format_telegram_daily_report(store_name, date_str, confirmed_orders)

        # 4. Send via Telegram
        sent_successfully = False
        error_message = None
        try:
            sent_successfully = await self.telegram_reporter.send_message(report_text)
            if not sent_successfully:
                error_message = "Telegram API returned False"
        except Exception as e:
            logger.exception("Failed to send daily report: %s", e)
            error_message = str(e)

        # 5. Save history record
        self.report_repo.save_report(
            store_id=store_id,
            report_date=target_date,
            report_content=report_text,
            sent_successfully=sent_successfully,
            error_message=error_message,
            # A manual resend after the nightly report must not clear its flag
            is_scheduled=(scheduled and sent_successfully) or nightly_already_sent,
        )

        return {
            "store_id": store_id,
            "report_date": date_str,
            "orders_count": len(confirmed_orders),
            "sent": sent_successfully,
            "error": error_message,
            "content": report_text,
        }
