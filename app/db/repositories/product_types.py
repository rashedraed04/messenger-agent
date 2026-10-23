"""
Product type repository for the admin-managed list of product kinds
(perfume, prayer rug, prayer beads, ...). A type decides which fields the
product form asks for and which illustration the storefront draws.
"""

import logging
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)

MAX_TYPE_NAME_LENGTH = 40
MAX_LABEL_LENGTH = 30

# Illustration key -> admin-facing label (drawn by storefront/_macros.html)
VISUALS: dict[str, str] = {
    "bottle": "زجاجة عطر",
    "rug": "سجادة صلاة",
    "beads": "مسبحة",
    "book": "مصحف / كتاب",
    "garment": "ملابس",
    "dates": "تمور / عبوة",
    "gift": "صندوق هدية",
}
DEFAULT_VISUAL = "gift"

# Bootstrap Icons shown for each illustration in the dashboard
VISUAL_ICONS: dict[str, str] = {
    "bottle": "bi-droplet-half",
    "rug": "bi-grid-3x3",
    "beads": "bi-circle",
    "book": "bi-book",
    "garment": "bi-person-standing-dress",
    "dates": "bi-basket",
    "gift": "bi-gift",
}

# Used when the product_types table is unavailable (demo mode / migration not applied)
DEFAULT_TYPES: list[dict[str, Any]] = [
    {"name_ar": "عطور ومسك", "visual": "bottle", "size_label": "الحجم", "size_unit": "مل", "details_label": "النوتات العطرية"},
    {"name_ar": "سجاد صلاة", "visual": "rug", "size_label": "المقاس", "size_unit": "سم", "details_label": "المميزات"},
    {"name_ar": "مسابح", "visual": "beads", "size_label": "عدد الحبات", "size_unit": "حبة", "details_label": "المميزات"},
    {"name_ar": "مصاحف وكتب", "visual": "book", "size_label": "الحجم", "size_unit": "سم", "details_label": "المميزات"},
    {"name_ar": "ملابس إحرام وعبايات", "visual": "garment", "size_label": "المقاس", "size_unit": None, "details_label": "المميزات"},
    {"name_ar": "تمور وماء زمزم", "visual": "dates", "size_label": "الوزن / الحجم", "size_unit": None, "details_label": "المميزات"},
    {"name_ar": "هدايا ومجموعات", "visual": "gift", "size_label": None, "size_unit": None, "details_label": "المحتويات"},
]
for _i, _t in enumerate(DEFAULT_TYPES, start=1):
    _t.update({"id": None, "show_in_filter": True, "sort_order": _i})

# Products saved before types existed: sized in ml means perfume
LEGACY_PERFUME = {"visual": "bottle", "size_label": "الحجم", "size_unit": "مل", "details_label": "النوتات العطرية"}
LEGACY_OTHER = {"visual": DEFAULT_VISUAL, "size_label": "الحجم", "size_unit": None, "details_label": "المميزات"}

EDITABLE_FIELDS = ("name_ar", "visual", "size_label", "size_unit", "details_label")


class ProductTypeUnavailableError(Exception):
    """Raised when types cannot be changed because the table is missing."""


def clean_type_fields(
    name_ar: str,
    visual: str,
    size_label: str | None,
    size_unit: str | None,
    details_label: str | None,
) -> dict[str, Any] | None:
    """Normalise form input; returns None when the name or labels are invalid."""
    name = " ".join((name_ar or "").split())
    if not name or len(name) > MAX_TYPE_NAME_LENGTH:
        return None
    labels = {
        "size_label": " ".join((size_label or "").split()) or None,
        "size_unit": " ".join((size_unit or "").split()) or None,
        "details_label": " ".join((details_label or "").split()) or "المميزات",
    }
    if any(v and len(v) > MAX_LABEL_LENGTH for v in labels.values()):
        return None
    if not labels["size_label"]:
        labels["size_unit"] = None
    return {
        "name_ar": name,
        "visual": visual if visual in VISUALS else DEFAULT_VISUAL,
        **labels,
    }


def describe_product(product: dict[str, Any], types_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Display info (visual, size label/unit, details label) for one product."""
    ptype = types_by_name.get(product.get("product_type") or "")
    if ptype:
        return {k: ptype.get(k) for k in ("visual", "size_label", "size_unit", "details_label")}
    if not product.get("product_type") and product.get("size_ml"):
        return dict(LEGACY_PERFUME)
    return dict(LEGACY_OTHER)


def format_size(product: dict[str, Any], info: dict[str, Any]) -> str:
    """'100 مل' / '120×80 سم' / free text; empty when the product has no size."""
    size = str(product.get("size_ml") or "").strip()
    if not size:
        return ""
    unit = info.get("size_unit")
    return f"{size} {unit}" if unit and unit not in size else size


def load_types_by_name(client: Any, store_id: str) -> dict[str, dict[str, Any]]:
    """
    Type definitions keyed by name for prompts and catalog formatting.
    Never raises: any failure (missing table, mocked client) yields the defaults.
    """
    try:
        types, _ = ProductTypeRepository(client).list_or_default(store_id)
        if isinstance(types, list):
            return {t["name_ar"]: t for t in types if isinstance(t, dict) and t.get("name_ar")}
    except Exception as e:
        logger.info("Product types unavailable for prompt: %s", e)
    return {t["name_ar"]: t for t in DEFAULT_TYPES}


class ProductTypeRepository:
    """Handles CRUD operations for product types."""

    def __init__(self, client: Client):
        self.client = client
        self.table = "product_types"
        self.products_table = "products"

    def list_by_store(self, store_id: str) -> list[dict[str, Any]]:
        """List all types of a store ordered for display (raises if the table is missing)."""
        res = (
            self.client.table(self.table)
            .select("*")
            .eq("store_id", store_id)
            .order("sort_order", desc=False)
            .order("name_ar", desc=False)
            .execute()
        )
        return res.data or []

    def list_or_default(self, store_id: str) -> tuple[list[dict[str, Any]], bool]:
        """(types, table_ready). Falls back to DEFAULT_TYPES if the table cannot be read."""
        try:
            return self.list_by_store(store_id), True
        except Exception as e:
            logger.info("Product type list fallback to defaults: %s", e)
            return [dict(t) for t in DEFAULT_TYPES], False

    def by_name(self, store_id: str) -> dict[str, dict[str, Any]]:
        types, _ = self.list_or_default(store_id)
        return {t["name_ar"]: t for t in types if t.get("name_ar")}

    def get_by_id(self, store_id: str, type_id: str) -> dict[str, Any] | None:
        try:
            res = (
                self.client.table(self.table)
                .select("*")
                .eq("store_id", store_id)
                .eq("id", type_id)
                .execute()
            )
        except Exception as e:
            raise ProductTypeUnavailableError(str(e)) from e
        return res.data[0] if res.data else None

    def exists(self, store_id: str, name_ar: str, exclude_id: str | None = None) -> bool:
        try:
            types = self.list_by_store(store_id)
        except Exception as e:
            raise ProductTypeUnavailableError(str(e)) from e
        return any(t["name_ar"] == name_ar and t.get("id") != exclude_id for t in types)

    def create(self, store_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        """Add a type at the end of the list."""
        try:
            existing = self.list_by_store(store_id)
        except Exception as e:
            raise ProductTypeUnavailableError(str(e)) from e

        next_order = max((t.get("sort_order") or 0 for t in existing), default=0) + 1
        payload = {"store_id": store_id, "sort_order": next_order, **fields}
        res = self.client.table(self.table).insert(payload).execute()
        return res.data[0] if res.data else {}

    def update(self, store_id: str, type_id: str, fields: dict[str, Any], old_name: str) -> None:
        """Update a type; a rename is carried over to the products using it."""
        payload = {k: v for k, v in fields.items() if k in EDITABLE_FIELDS}
        self.client.table(self.table).update(payload).eq("store_id", store_id).eq("id", type_id).execute()
        new_name = payload.get("name_ar")
        if new_name and new_name != old_name:
            self.client.table(self.products_table).update({"product_type": new_name}).eq(
                "store_id", store_id
            ).eq("product_type", old_name).execute()

    def set_filter_visibility(self, store_id: str, type_id: str, visible: bool) -> None:
        self.client.table(self.table).update({"show_in_filter": visible}).eq(
            "store_id", store_id
        ).eq("id", type_id).execute()

    def move(self, store_id: str, type_id: str, direction: int) -> None:
        """Swap a type with its neighbour (direction -1 = up, +1 = down)."""
        try:
            types = self.list_by_store(store_id)
        except Exception as e:
            raise ProductTypeUnavailableError(str(e)) from e
        reorder_rows(self.client, self.table, store_id, types, type_id, direction)

    def delete(self, store_id: str, type_id: str) -> None:
        self.client.table(self.table).delete().eq("store_id", store_id).eq("id", type_id).execute()

    def count_products(self, store_id: str) -> dict[str, int]:
        """Map type name -> number of products using it."""
        try:
            res = (
                self.client.table(self.products_table)
                .select("product_type")
                .eq("store_id", store_id)
                .execute()
            )
        except Exception:
            return {}
        counts: dict[str, int] = {}
        for row in res.data or []:
            name = row.get("product_type")
            if name:
                counts[name] = counts.get(name, 0) + 1
        return counts


def reorder_rows(
    client: Client,
    table: str,
    store_id: str,
    rows: list[dict[str, Any]],
    row_id: str,
    direction: int,
) -> bool:
    """
    Move one row up/down in a sort_order list by renumbering the list 1..n.
    Shared by categories and product types. Returns False if the move is impossible.
    """
    ids = [r.get("id") for r in rows]
    if row_id not in ids:
        return False
    i = ids.index(row_id)
    j = i + direction
    if j < 0 or j >= len(ids):
        return False
    ids[i], ids[j] = ids[j], ids[i]
    current = {r.get("id"): r.get("sort_order") for r in rows}
    for order, rid in enumerate(ids, start=1):
        if current.get(rid) != order:
            client.table(table).update({"sort_order": order}).eq("store_id", store_id).eq("id", rid).execute()
    return True
