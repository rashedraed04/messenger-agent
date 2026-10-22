"""
Report repository for database operations on report_history table.
"""

from datetime import date, datetime, timezone
from typing import Any
from supabase import Client


class ReportRepository:
    """Handles persistence and retrieval of daily report records."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "report_history"

    def get_by_date(
        self, store_id: str, report_date: date
    ) -> dict[str, Any] | None:
        """Fetch report record for a specific date."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("report_date", report_date.isoformat())
            .execute()
        )
        return res.data[0] if res.data else None

    def save_report(
        self,
        store_id: str,
        report_date: date,
        report_content: str,
        sent_successfully: bool,
        error_message: str | None = None,
        is_scheduled: bool = False,
    ) -> dict[str, Any]:
        """Upsert a daily report record."""
        payload = {
            "store_id": store_id,
            "report_date": report_date.isoformat(),
            "report_content": report_content,
            "sent_successfully": sent_successfully,
            "error_message": error_message,
            "is_scheduled": is_scheduled,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        res = (
            self.client.table(self.table)
            .upsert(payload, on_conflict="store_id,report_date")
            .execute()
        )
        return res.data[0] if res.data else {}

    def list_history(
        self, store_id: str, limit: int = 30
    ) -> list[dict[str, Any]]:
        """List past reports ordered by date descending."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .order("report_date", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
