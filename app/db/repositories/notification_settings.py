"""
Notification settings repository for database operations on notification_settings table.
Enforces multi-tenant store_id isolation.
"""

from typing import Any

from supabase import Client

from app.models.notification_setting import (
    NotificationSettingUpdate,
)


class NotificationSettingRepository:
    """Handles channel notification and daily reporting preferences per store."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "notification_settings"

    def get_by_channel(
        self, store_id: str, channel: str = "telegram"
    ) -> dict[str, Any] | None:
        """Fetch notification settings for a specific channel and store."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("channel", channel)
            .execute()
        )
        if res.data:
            return res.data[0]
        return None

    def list_by_store(self, store_id: str) -> list[dict[str, Any]]:
        """List all notification channel configurations for a store."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .order("channel")
            .execute()
        )
        return res.data or []

    def upsert(
        self,
        store_id: str,
        channel: str,
        updates: NotificationSettingUpdate | dict[str, Any],
    ) -> dict[str, Any]:
        """
        Upsert notification settings for a store and channel.
        Guarantees store_id isolation.
        """
        if isinstance(updates, NotificationSettingUpdate):
            payload = updates.model_dump(exclude_unset=True)
        else:
            payload = dict(updates)

        payload["store_id"] = store_id
        payload["channel"] = channel

        res = (
            self.client.table(self.table)
            .upsert(payload, on_conflict="store_id,channel")
            .execute()
        )
        return res.data[0] if res.data else {}

    def should_send_daily_report(
        self, store_id: str, channel: str = "telegram"
    ) -> bool:
        """Check if daily report is enabled for store channel."""
        cfg = self.get_by_channel(store_id, channel)
        if not cfg:
            return True  # Default enabled if row not yet configured
        return bool(cfg.get("daily_report_enabled", True))
