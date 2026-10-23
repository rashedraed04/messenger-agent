"""
Store repository for database operations on stores table.
"""

from typing import Any
from supabase import Client


class StoreRepository:
    """Handles multi-store metadata operations."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "stores"

    def get_by_id(self, store_id: str) -> dict[str, Any] | None:
        """Fetch store by ID."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("id", store_id)
            .execute()
        )
        return res.data[0] if res.data else None
