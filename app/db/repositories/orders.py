"""
Order repository for database operations on orders and order_items tables.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import secrets
from typing import Any
from dateutil import tz
from supabase import Client

from app.models.order import OrderCreate, OrderItemCreate, OrderStatus

AMMAN_TZ = tz.gettz("Asia/Amman") or timezone(timedelta(hours=3))


class OrderRepository:
    """Handles CRUD operations for orders and their line items."""

    def __init__(self, client: Client):
        self.client = client
        self.orders_table = "orders"
        self.items_table = "order_items"

    def generate_order_number(self, store_id: str) -> str:
        """
        Generate human-friendly unique order number: ORD-YYYYMMDD-XXXX
        e.g., ORD-20261017-A1B2
        """
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        suffix = secrets.token_hex(2).upper()
        return f"ORD-{today_str}-{suffix}"

    def create_order(
        self,
        store_id: str,
        order_data: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Create a new order along with its order_items.
        Ensures unit prices and product names are snapshotted.
        """
        payload = dict(order_data)
        payload["store_id"] = store_id
        if "order_number" not in payload or not payload["order_number"]:
            payload["order_number"] = self.generate_order_number(store_id)

        # Convert Decimal values to float for JSON serialization
        for key in ("subtotal_jod", "delivery_fee_jod", "total_jod"):
            if key in payload and isinstance(payload[key], Decimal):
                payload[key] = float(payload[key])

        res = self.client.table(self.orders_table).insert(payload).execute()
        if not res.data:
            raise RuntimeError("Failed to create order")

        created_order = res.data[0]
        order_id = created_order["id"]

        # Insert items
        items_payload = []
        for item in items:
            item_row = {
                "order_id": order_id,
                "product_id": item.get("product_id"),
                "product_name_snapshot": item["product_name_snapshot"],
                "unit_price_snapshot": float(item["unit_price_snapshot"])
                if isinstance(item["unit_price_snapshot"], Decimal)
                else item["unit_price_snapshot"],
                "quantity": item["quantity"],
                "line_total_jod": float(item["line_total_jod"])
                if isinstance(item["line_total_jod"], Decimal)
                else item["line_total_jod"],
            }
            items_payload.append(item_row)

        if items_payload:
            items_res = self.client.table(self.items_table).insert(items_payload).execute()
            created_order["items"] = items_res.data or []
        else:
            created_order["items"] = []

        return created_order

    def list_by_store(self, store_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Most recent orders for a store."""
        query = (
            self.client.table(self.orders_table)
            .select("*, order_items(*)")
            .eq("store_id", store_id)
            .order("created_at", desc=True)
        )

        res = query.limit(limit).execute()
        orders = res.data or []
        for o in orders:
            o["items"] = o.get("order_items", [])
        return orders

    def get_confirmed_orders_by_date(
        self, store_id: str, target_date: date
    ) -> list[dict[str, Any]]:
        """
        Fetch all confirmed orders for a specific date (for daily Telegram reports).
        Matches confirmed_at within that day's Asia/Amman midnight-to-midnight.
        """
        start_of_day = datetime.combine(target_date, time.min, tzinfo=AMMAN_TZ)
        end_of_day = start_of_day + timedelta(days=1)

        res = (
            self.client.table(self.orders_table)
            .select("*, order_items(*)")
            .eq("store_id", store_id)
            .gte("confirmed_at", start_of_day.isoformat())
            .lt("confirmed_at", end_of_day.isoformat())
            .neq("status", OrderStatus.CANCELLED.value)
            .order("confirmed_at", desc=False)
            .execute()
        )
        orders = res.data or []
        for o in orders:
            o["items"] = o.get("order_items", [])
        return orders
