"""
FAQ repository for database operations on faqs table.
"""

from typing import Any
from supabase import Client

from app.models.faq import FAQCreate, FAQUpdate


class FAQRepository:
    """Handles CRUD operations for frequently asked questions."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "faqs"

    def list_active(self, store_id: str) -> list[dict[str, Any]]:
        """Fetch all active FAQs ordered by sort_order for prompt injection."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("is_active", True)
            .order("sort_order", desc=False)
            .execute()
        )
        return res.data or []

    def list_all(self, store_id: str) -> list[dict[str, Any]]:
        """Fetch all FAQs for dashboard management."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .order("sort_order", desc=False)
            .execute()
        )
        return res.data or []

    def get_by_id(self, store_id: str, faq_id: str) -> dict[str, Any] | None:
        """Fetch a single FAQ by ID."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("id", faq_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def create(self, store_id: str, faq: FAQCreate) -> dict[str, Any]:
        """Create a new FAQ."""
        payload = faq.model_dump()
        payload["store_id"] = store_id
        res = self.client.table(self.table).insert(payload).execute()
        return res.data[0] if res.data else {}

    def update(
        self, store_id: str, faq_id: str, updates: FAQUpdate | dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an existing FAQ."""
        if isinstance(updates, FAQUpdate):
            payload = updates.model_dump(exclude_unset=True)
        else:
            payload = dict(updates)

        res = (
            self.client.table(self.table)
            .update(payload)
            .eq("store_id", store_id)
            .eq("id", faq_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def delete(self, store_id: str, faq_id: str) -> bool:
        """Delete an FAQ."""
        res = (
            self.client.table(self.table)
            .delete()
            .eq("store_id", store_id)
            .eq("id", faq_id)
            .execute()
        )
        return bool(res.data)
