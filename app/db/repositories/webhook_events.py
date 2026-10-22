"""
Webhook event repository for idempotency handling.
"""

from typing import Any
from supabase import Client


class WebhookEventRepository:
    """Handles idempotency for incoming Meta webhooks using message IDs (mid)."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "processed_webhook_events"

    def is_processed(self, store_id: str, event_mid: str) -> bool:
        """Check if an event mid has already been processed."""
        res = (
            self.client.table(self.table)
            .select("id")
            .eq("store_id", store_id)
            .eq("event_mid", event_mid)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def mark_processed_if_new(
        self,
        store_id: str,
        event_mid: str,
        event_type: str = "message",
    ) -> bool:
        """
        Atomically records an event mid if it has not been processed yet.
        Returns True if newly inserted, False if it already existed.
        """
        # In Supabase postgrest, we can check existing or insert
        if self.is_processed(store_id, event_mid):
            return False

        try:
            payload = {
                "store_id": store_id,
                "event_mid": event_mid,
                "event_type": event_type,
            }
            res = self.client.table(self.table).insert(payload).execute()
            return bool(res.data)
        except Exception:
            # If unique constraint violation occurs during race condition
            return False
