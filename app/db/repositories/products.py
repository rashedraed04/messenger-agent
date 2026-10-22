"""
Product repository for database operations on products table.
"""

from decimal import Decimal
import logging
from typing import Any
from supabase import Client

from app.db.repositories.search import build_ilike_or_filter, clean_search_term
from app.models.product import ProductCreate, ProductUpdate

logger = logging.getLogger(__name__)


class ProductRepository:
    """Handles CRUD and search operations for products."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "products"

    def list_by_store(
        self,
        store_id: str,
        only_active: bool = False,
        category: str | None = None,
        search_query: str | None = None,
        limit: int = 150,
        offset: int = 0,
        product_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """List products for a store with optional filtering."""
        term = clean_search_term(search_query)
        try:
            query = (
                self.client.table(self.table)
                .select("*")
                .eq("store_id", store_id)
                .order("sort_order", desc=False)
                .order("created_at", desc=True)
            )

            if only_active:
                query = query.eq("is_active", True)
            if category:
                query = query.eq("category", category)
            if product_type:
                query = query.eq("product_type", product_type)
            if term:
                # Case-insensitive substring match on names, brand and notes
                query = query.or_(
                    build_ilike_or_filter(["name_ar", "name_en", "brand", "tags"], term)
                )

            query = query.range(offset, offset + limit - 1)
            return query.execute().data or []
        except Exception as e:
            logger.warning("Could not list products for store %s: %s", store_id, e)
            return []

    def get_public_showcase(
        self,
        store_id: str,
        search_query: str | None = None,
        category: str | None = None,
        product_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch products for the public customer storefront.

        CRITICAL REQUIREMENT:
        Strictly strips price_jod so no prices exist in HTML or public data.
        Only returns active products.
        """
        raw_products = self.list_by_store(
            store_id=store_id,
            only_active=True,
            category=category,
            search_query=search_query,
            limit=150,
            product_type=product_type,
        )

        showcase_items = []
        for p in raw_products:
            item = dict(p)
            # CRITICAL: Strip price_jod completely for public page
            item.pop("price_jod", None)
            showcase_items.append(item)

        return showcase_items

    def get_public_by_id(self, store_id: str, product_id: str) -> dict[str, Any] | None:
        """
        Fetch one active, in-stock product for the public detail page.
        CRITICAL: price_jod is stripped exactly like get_public_showcase.
        """
        product = self.get_by_id(store_id, product_id)
        if not product or not product.get("is_active"):
            return None
        product.pop("price_jod", None)
        return product

    def get_by_id(self, store_id: str, product_id: str) -> dict[str, Any] | None:
        """Fetch a single product by ID ensuring store isolation."""
        try:
            res = (
                self.client.table(self.table)
                .select("*")
                .eq("store_id", store_id)
                .eq("id", product_id)
                .execute()
            )
            if res.data:
                return res.data[0]
        except Exception as e:
            logger.warning("Could not fetch product %s: %s", product_id, e)

        return None

    def get_active_catalog(self, store_id: str) -> list[dict[str, Any]]:
        """Fetch all active products for AI context and recommendations."""
        try:
            res = (
                self.client.table(self.table)
                .select("*")
                .eq("store_id", store_id)
                .eq("is_active", True)
                .order("sort_order", desc=False)
                .execute()
            )
            if res.data:
                return res.data
        except Exception as e:
            logger.warning("Could not load active catalog for store %s: %s", store_id, e)

        return []

    def create(self, store_id: str, product: ProductCreate) -> dict[str, Any]:
        """Create a new product."""
        payload = product.model_dump()
        payload["store_id"] = store_id
        if isinstance(payload.get("price_jod"), Decimal):
            payload["price_jod"] = float(payload["price_jod"])

        res = self._write_with_type_fallback(
            payload, lambda data: self.client.table(self.table).insert(data).execute()
        )
        return res.data[0] if res.data else {}

    def update(
        self, store_id: str, product_id: str, updates: ProductUpdate | dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an existing product."""
        if isinstance(updates, ProductUpdate):
            payload = updates.model_dump(exclude_unset=True)
        else:
            payload = dict(updates)

        if "price_jod" in payload and isinstance(payload["price_jod"], Decimal):
            payload["price_jod"] = float(payload["price_jod"])

        res = self._write_with_type_fallback(
            payload,
            lambda data: self.client.table(self.table)
            .update(data)
            .eq("store_id", store_id)
            .eq("id", product_id)
            .execute(),
        )
        return res.data[0] if res.data else None

    @staticmethod
    def _write_with_type_fallback(payload: dict[str, Any], write: Any) -> Any:
        """
        Run an insert/update; if the database predates migration 004 (no
        products.product_type column), retry once without that field.
        """
        try:
            return write(payload)
        except Exception as e:
            if "product_type" not in str(e) or "product_type" not in payload:
                raise
            logger.warning("products.product_type missing (run migration 004); saving without it")
            return write({k: v for k, v in payload.items() if k != "product_type"})

    def delete(self, store_id: str, product_id: str) -> bool:
        """Delete a product."""
        res = (
            self.client.table(self.table)
            .delete()
            .eq("store_id", store_id)
            .eq("id", product_id)
            .execute()
        )
        return bool(res.data)
