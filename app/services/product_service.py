"""
Product service with Arabic fuzzy matching and catalog helpers.
"""

import re
from typing import Any
from app.db.repositories.products import ProductRepository


def normalize_arabic_text(text: str) -> str:
    """
    Normalize Arabic text for fuzzy comparison:
    - Unify alef variations (أ, إ, آ -> ا)
    - Unify taa marbuta / haa (ة -> ه)
    - Unify yaa / alef maksura (ى -> ي)
    - Remove diacritics / tashkeel
    - Remove tatweel (ـ)
    - Lowercase ASCII
    """
    if not text:
        return ""

    # Remove tashkeel / diacritics
    text = re.sub(r"[\u064B-\u0652\u0670]", "", text)
    # Remove tatweel
    text = re.sub(r"\u0640", "", text)

    # Normalize alef
    text = re.sub(r"[أإآٱ]", "ا", text)
    # Normalize taa marbuta
    text = text.replace("ة", "ه")
    # Normalize alef maksura
    text = text.replace("ى", "ي")

    return text.strip().lower()


class ProductService:
    """High-level product catalog operations and fuzzy matching."""

    def __init__(self, product_repo: ProductRepository):
        self.product_repo = product_repo

    def match_product_by_name(
        self, store_id: str, query: str
    ) -> dict[str, Any] | None:
        """
        Fuzzy match a customer inquiry against active products in the store catalog.

        Args:
            store_id: Store ID.
            query: The product name mentioned by the customer.

        Returns:
            The matched product dict if found, else None.
        """
        if not query:
            return None

        clean_query = normalize_arabic_text(query)
        # Strip common Arabic query prefixes like "عطر", "بدي", "علبة"
        clean_query = re.sub(r"^(عطر|بدي عطر|بدي|علبه|علبة)\s+", "", clean_query).strip()

        catalog = self.product_repo.get_active_catalog(store_id)
        if not catalog:
            return None

        best_match = None
        best_score = 0

        query_tokens = set(clean_query.split())

        for prod in catalog:
            name_ar = normalize_arabic_text(prod.get("name_ar") or "")
            name_en = (prod.get("name_en") or "").lower()
            brand = normalize_arabic_text(prod.get("brand") or "")
            tags = normalize_arabic_text(prod.get("tags") or "")

            # Exact match on name
            if clean_query == name_ar or clean_query == name_en:
                return prod

            # Substring match (e.g., "سوفاج" inside "سوفاج ديور 100 مل")
            if clean_query and (clean_query in name_ar or clean_query in name_en):
                return prod

            if name_ar and name_ar in clean_query:
                return prod

            # Token overlap scoring
            target_tokens = set(name_ar.split() + name_en.split() + brand.split() + tags.split(","))
            overlap = query_tokens.intersection(target_tokens)
            score = len(overlap)

            if score > best_score:
                best_score = score
                best_match = prod

        # Return best match if at least one meaningful token overlapped
        if best_score > 0:
            return best_match

        return None

    def check_available(self, store_id: str, product_id: str) -> tuple[bool, str]:
        """
        Check the product still exists and is active (quantities are not tracked).

        Returns:
            (is_available, message_ar)
        """
        product = self.product_repo.get_by_id(store_id, product_id)
        if not product:
            return False, "المنتج غير موجود"

        if not product.get("is_active"):
            return False, "المنتج غير متوفر حالياً"

        return True, "متوفر"
