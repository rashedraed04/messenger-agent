"""
Customer repository for database operations on customers table.
"""

from datetime import UTC, datetime
from typing import Any

from supabase import Client


class CustomerRepository:
    """Handles CRUD operations for customers identified by Messenger PSID."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "customers"

    def get_by_psid(self, store_id: str, messenger_psid: str) -> dict[str, Any] | None:
        """Fetch customer by store_id and PSID."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("messenger_psid", messenger_psid)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_by_id(self, store_id: str, customer_id: str) -> dict[str, Any] | None:
        """Fetch customer by ID."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .eq("id", customer_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def get_or_create(
        self,
        store_id: str,
        messenger_psid: str,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fetch existing customer or create a new one."""
        existing = self.get_by_psid(store_id, messenger_psid)
        if existing:
            # Update name if provided and not previously recorded
            if name and not existing.get("name"):
                self.update(store_id, existing["id"], {"name": name})
                existing["name"] = name
            return existing

        now_iso = datetime.now(UTC).isoformat()
        payload = {
            "store_id": store_id,
            "messenger_psid": messenger_psid,
            "name": name,
            "total_orders": 0,
            "first_contact_at": now_iso,
            "last_contact_at": now_iso,
        }
        res = self.client.table(self.table).insert(payload).execute()
        return res.data[0] if res.data else {}

    def update(
        self, store_id: str, customer_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update customer fields."""
        payload = dict(updates)
        payload["last_contact_at"] = datetime.now(UTC).isoformat()

        res = (
            self.client.table(self.table)
            .update(payload)
            .eq("store_id", store_id)
            .eq("id", customer_id)
            .execute()
        )
        return res.data[0] if res.data else None

    def record_order_placed(
        self,
        store_id: str,
        customer_id: str,
        name: str | None = None,
        phone_normalized: str | None = None,
        governorate: str | None = None,
        address_detail: str | None = None,
    ) -> None:
        """Update customer info and increment order count after an order is placed."""
        current = self.get_by_id(store_id, customer_id)
        if not current:
            return

        updates: dict[str, Any] = {
            "total_orders": (current.get("total_orders") or 0) + 1,
            "last_contact_at": datetime.now(UTC).isoformat(),
        }
        if name:
            updates["name"] = name
        if phone_normalized:
            updates["phone_normalized"] = phone_normalized
        if governorate:
            updates["governorate"] = governorate
        if address_detail:
            updates["address_detail"] = address_detail

        self.update(store_id, customer_id, updates)

