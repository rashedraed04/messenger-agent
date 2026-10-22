"""
Product category repository for the admin-managed category list.
"""

import logging
from typing import Any
from supabase import Client

from app.db.repositories.product_types import reorder_rows

logger = logging.getLogger(__name__)

# Used when the product_categories table is unavailable (demo mode / migration not applied)
DEFAULT_CATEGORIES = ["رجالي", "نسائي", "للجنسين", "شرقي"]
MAX_CATEGORY_NAME_LENGTH = 40


class CategoryUnavailableError(Exception):
    """Raised when categories cannot be changed because the table is missing."""


class CategoryRepository:
    """Handles CRUD operations for product categories."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "product_categories"
        self.products_table = "products"

    def list_by_store(self, store_id: str) -> list[dict[str, Any]]:
        """List all categories of a store ordered for display."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .order("sort_order", desc=False)
            .order("name_ar", desc=False)
            .execute()
        )
        return res.data or []

    def get_names(self, store_id: str, only_filter_visible: bool = False) -> list[str]:
        """
        Return category names for dropdowns and storefront filters.
        Falls back to DEFAULT_CATEGORIES if the table cannot be read.
        """
        try:
            categories = self.list_by_store(store_id)
        except Exception as e:
            logger.info("Category list fallback to defaults: %s", e)
            return list(DEFAULT_CATEGORIES)

        if only_filter_visible:
            categories = [c for c in categories if c.get("show_in_filter")]
        return [c["name_ar"] for c in categories]

    def create(self, store_id: str, name_ar: str) -> dict[str, Any]:
        """Add a category at the end of the list."""
        try:
            existing = self.list_by_store(store_id)
        except Exception as e:
            raise CategoryUnavailableError(str(e)) from e

        next_order = max((c.get("sort_order") or 0 for c in existing), default=0) + 1
        res = (
            self.client.table(self.table)
            .insert({"store_id": store_id, "name_ar": name_ar, "sort_order": next_order})
            .execute()
        )
        return res.data[0] if res.data else {}

    def exists(self, store_id: str, name_ar: str) -> bool:
        try:
            names = [c["name_ar"] for c in self.list_by_store(store_id)]
        except Exception as e:
            raise CategoryUnavailableError(str(e)) from e
        return name_ar in names

    def get_by_id(self, store_id: str, category_id: str) -> dict[str, Any] | None:
        try:
            res = (
                self.client.table(self.table)
                .select("*")
                .eq("store_id", store_id)
                .eq("id", category_id)
                .execute()
            )
        except Exception as e:
            raise CategoryUnavailableError(str(e)) from e
        return res.data[0] if res.data else None

    def set_filter_visibility(self, store_id: str, category_id: str, visible: bool) -> None:
        self.client.table(self.table).update({"show_in_filter": visible}).eq(
            "store_id", store_id
        ).eq("id", category_id).execute()

    def rename(self, store_id: str, category_id: str, old_name: str, new_name: str) -> None:
        """Rename a category and carry the new name over to its products."""
        self.client.table(self.table).update({"name_ar": new_name}).eq(
            "store_id", store_id
        ).eq("id", category_id).execute()
        self.client.table(self.products_table).update({"category": new_name}).eq(
            "store_id", store_id
        ).eq("category", old_name).execute()

    def move(self, store_id: str, category_id: str, direction: int) -> None:
        """Swap a category with its neighbour (direction -1 = up, +1 = down)."""
        try:
            categories = self.list_by_store(store_id)
        except Exception as e:
            raise CategoryUnavailableError(str(e)) from e
        reorder_rows(self.client, self.table, store_id, categories, category_id, direction)

    def delete(self, store_id: str, category_id: str) -> None:
        self.client.table(self.table).delete().eq("store_id", store_id).eq(
            "id", category_id
        ).execute()

    def count_products(self, store_id: str) -> dict[str, int]:
        """Map category name -> number of products using it."""
        try:
            res = (
                self.client.table(self.products_table)
                .select("category")
                .eq("store_id", store_id)
                .execute()
            )
        except Exception:
            return {}
        counts: dict[str, int] = {}
        for row in res.data or []:
            name = row.get("category")
            if name:
                counts[name] = counts.get(name, 0) + 1
        return counts
