"""
Order service and state machine orchestrator.

Coordinates:
- Slot merging (handles step-by-step and all-in-one messages)
- Slot validation (products, phone, governorate, address)
- Price calculation (pure Python, 3 decimal places)
- State machine transitions
- Order placement
"""

from datetime import datetime, timezone
import re
from typing import Any
from app.db.repositories.conversations import ConversationRepository
from app.db.repositories.customers import CustomerRepository
from app.db.repositories.orders import OrderRepository
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.models.conversation import ConversationState
from app.models.order import OrderStatus
from app.services.governorates import match_governorate
from app.services.phone_normalizer import normalize_jordanian_phone, PhoneValidationError
from app.services.price_calculator import calculate_order_totals, OrderPriceSummary
from app.services.product_service import ProductService, normalize_arabic_text

# Customer-typed fields are fed back into the AI prompt and the courier report,
# so cap them: no essay-length "addresses" carrying instructions for the bot
MAX_NAME_LENGTH = 100
MAX_ADDRESS_LENGTH = 300
MAX_QUANTITY = 100

REQUIRED_SLOTS = ("products", "customer_name", "customer_phone", "governorate", "address_detail")

# Arabic confirmation affirmative keywords
AFFIRMATIVE_KEYWORDS = {
    "نعم", "ايوه", "ايوا", "تمام", "اوكي", "اوك", "اكيد", "أكيد", "اه", "أه",
    "موافق", "اعتمد", "اعتمدها", "اعتمده", "اعتمدلي", "اعتمدو", "ثبت", "ثبته", "ثبتها",
    "توكلنا", "توكل على الله", "يلا", "صح", "صحيح", "yes", "ok"
}

# Phrases that explicitly abort the whole order (matched on normalized text).
# Note: a bare "لا" is NOT here — "لا بدي سوفاج بس" is a modification, not a cancellation.
EXPLICIT_CANCEL_PHRASES = (
    "الغاء", "الغي", "كنسل", "cancel", "ما بدي اطلب", "ما بدي الطلب", "مش بدي اطلب",
    "بديش الطلب", "بديش اياه", "بطلت", "هونت", "غيرت رايي", "بلاش الطلب",
)

# A message made up only of these tokens is a plain "no" (e.g. "لا", "لا شكرا", "ما بدي")
BARE_NEGATIVE_TOKENS = {"لا", "لاء", "كلا", "بديش", "شكرا", "مشكور", "خلص", "no", "nope", "thanks"}

# Words signalling the customer wants ONLY the item they just named ("لا بدي سوفاج بس")
EXCLUSIVE_MARKERS = {"بس", "فقط", "بلحالها", "لحالها", "لحاله", "only"}

# Words signalling a change request; an affirmative next to these is not a confirmation
MODIFICATION_MARKERS = EXCLUSIVE_MARKERS | {"بدل", "غير", "غيرها", "غيره", "خليها", "خليه", "عدل", "عدلها"}

SLOT_KEYS = ("products", "customer_name", "customer_phone", "governorate", "address_detail")

# Arabic human handover trigger keywords
HANDOFF_KEYWORDS = {
    "بدي احكي مع انسان", "بدي موظف", "حولني", "خدمة العملاء", "بدي شخص",
    "مش فاهم", "ما عم تفهمني", "مسؤول", "بدي حدا يفهمني", "human", "agent"
}


def _tokens(normalized_text: str) -> list[str]:
    """Split normalized text into word tokens, dropping punctuation and emoji."""
    return re.findall(r"[\w]+", normalized_text)


def has_slot_values(extracted_slots: dict[str, Any] | None) -> bool:
    """True if the AI extracted any concrete order detail (product, name, phone, address...)."""
    if not extracted_slots:
        return False
    return any(extracted_slots.get(key) for key in SLOT_KEYS)


def is_cancellation_request(
    user_message: str,
    extracted_slots: dict[str, Any] | None = None,
    intent: str | None = None,
) -> bool:
    """
    Decide whether the customer wants to abort the entire order.

    A message carrying a replacement detail ("لا بدي سوفاج بس", "لا خليها لعمان")
    is a modification, never a cancellation — unless the AI itself classified it
    as cancel_order alongside an explicit cancel phrase.
    """
    text = normalize_arabic_text(user_message)
    modifies = has_slot_values(extracted_slots)
    wants_cancel = intent == "cancel_order"

    if any(phrase in text for phrase in EXPLICIT_CANCEL_PHRASES):
        return wants_cancel or not modifies

    if modifies:
        return False

    if wants_cancel:
        return True

    # Plain refusal with nothing else in it: "لا", "لا شكراً", "ما بدي"
    remaining = _tokens(text.replace("ما بدي", " "))
    had_content = bool(_tokens(text))
    return had_content and all(tok in BARE_NEGATIVE_TOKENS for tok in remaining)


GENERIC_PRODUCT_WORDS = {"عطر", "مل", "ml", "edp", "edt", "parfum", "perfume", "دي", "de"}


def _product_name_tokens(product: dict[str, Any]) -> set[str]:
    """Distinctive name tokens of a catalog product (e.g. {"سوفاج", "ديور", "sauvage", "dior"})."""
    raw = f"{normalize_arabic_text(product.get('name_ar') or '')} {(product.get('name_en') or '').lower()}"
    return {
        tok for tok in _tokens(raw)
        if len(tok) >= 3 and not tok.isdigit() and tok not in GENERIC_PRODUCT_WORDS
    }


def is_exclusive_selection(user_message: str) -> bool:
    """True when the customer says they want ONLY the named item ("بس" / "فقط")."""
    return any(tok in EXCLUSIVE_MARKERS for tok in _tokens(normalize_arabic_text(user_message)))


class OrderService:
    """Manages conversational order state and fulfillment."""

    def __init__(
        self,
        order_repo: OrderRepository,
        product_repo: ProductRepository,
        setting_repo: StoreSettingRepository,
        conversation_repo: ConversationRepository,
        customer_repo: CustomerRepository,
    ):
        self.order_repo = order_repo
        self.product_repo = product_repo
        self.setting_repo = setting_repo
        self.conversation_repo = conversation_repo
        self.customer_repo = customer_repo
        self.product_service = ProductService(product_repo)

    def validate_and_merge_slots(
        self,
        store_id: str,
        existing_slots: dict[str, Any],
        new_slots: dict[str, Any],
    ) -> tuple[dict[str, Any], list[str]]:
        """
        Merge new slots into existing slots with validation.

        Returns:
            (merged_slots, missing_slot_names)
        """
        merged = dict(existing_slots or {})

        # 1. Products
        if "products" in new_slots and new_slots["products"]:
            validated_products = []
            for p in new_slots["products"]:
                # If product_id already known
                p_id = p.get("product_id")
                prod = None
                if p_id:
                    prod = self.product_repo.get_by_id(store_id, p_id)
                elif p.get("name_match"):
                    prod = self.product_service.match_product_by_name(store_id, p["name_match"])

                if prod and prod.get("is_active", True):
                    try:
                        qty = min(int(p.get("quantity") or 1), MAX_QUANTITY)
                    except (TypeError, ValueError):
                        qty = 1
                    if qty > 0:
                        validated_products.append({
                            "product_id": prod["id"],
                            "product_name": prod["name_ar"],
                            "unit_price_jod": float(prod["price_jod"]),
                            "quantity": qty,
                        })
            if validated_products:
                merged["products"] = validated_products

        # 2. Customer Name
        if new_slots.get("customer_name"):
            name = str(new_slots["customer_name"]).strip()[:MAX_NAME_LENGTH]
            if len(name) >= 2:
                merged["customer_name"] = name

        # 3. Customer Phone
        if new_slots.get("customer_phone"):
            try:
                normalized_phone = normalize_jordanian_phone(str(new_slots["customer_phone"]))
                merged["customer_phone"] = normalized_phone
            except PhoneValidationError:
                pass  # Keep existing phone if invalid new one provided

        # 4. Governorate
        if new_slots.get("governorate"):
            governorate = match_governorate(str(new_slots["governorate"]))
            if governorate:
                merged["governorate"] = governorate
                merged["delivery_fee_jod"] = self.setting_repo.get_delivery_fee(store_id)

        # 5. Address Detail
        if new_slots.get("address_detail"):
            addr = str(new_slots["address_detail"]).strip()[:MAX_ADDRESS_LENGTH]
            if len(addr) >= 3:
                merged["address_detail"] = addr

        # Determine missing slots
        missing = [slot for slot in REQUIRED_SLOTS if not merged.get(slot)]

        return merged, missing

    def calculate_price_summary(
        self, store_id: str, collected_slots: dict[str, Any]
    ) -> OrderPriceSummary | None:
        """Calculate order totals (products + the store's flat delivery fee)."""
        products = collected_slots.get("products")
        if not products:
            return None

        fee = self.setting_repo.get_delivery_fee(store_id)
        gov = collected_slots.get("governorate")
        return calculate_order_totals(products, delivery_fee_jod=fee, governorate=gov)

    def process_state_transition(
        self,
        store_id: str,
        current_state: ConversationState,
        collected_slots: dict[str, Any],
        user_message: str,
        extracted_slots: dict[str, Any] | None = None,
        intent: str | None = None,
    ) -> tuple[ConversationState, dict[str, Any], str]:
        """
        State machine transition logic based on current state, slots, and user message.

        Returns:
            (next_state, updated_slots, system_action_or_note)
        """
        clean_text = user_message.strip().lower()
        normalized_tokens = set(_tokens(normalize_arabic_text(user_message)))

        # Check for explicit human handoff request in ANY pre-confirmed state
        for kw in HANDOFF_KEYWORDS:
            if kw in clean_text:
                return (
                    ConversationState.HUMAN_HANDOFF,
                    collected_slots,
                    "Customer explicitly requested human agent",
                )

        # Check for explicit cancellation
        if current_state in (
            ConversationState.PRODUCT_SELECTION,
            ConversationState.COLLECTING_DETAILS,
            ConversationState.AWAITING_CONFIRMATION,
        ) and is_cancellation_request(user_message, extracted_slots, intent):
            return (
                ConversationState.CANCELLED,
                {},
                "Customer cancelled the order",
            )

        # Handle AWAITING_CONFIRMATION response ("اه بس بدي سوفاج" is a change, not a yes)
        if current_state == ConversationState.AWAITING_CONFIRMATION:
            tokens = set(clean_text.split())
            is_affirmative = any(kw in tokens or clean_text == kw for kw in AFFIRMATIVE_KEYWORDS)
            is_change = intent == "modify_order" or bool(normalized_tokens & MODIFICATION_MARKERS)
            if is_affirmative and not is_change:
                return (
                    ConversationState.CONFIRMED,
                    collected_slots,
                    "Customer confirmed the order summary",
                )

        # Merge slots if any were extracted
        merged_slots = dict(collected_slots)
        if extracted_slots:
            merged_slots, _ = self.validate_and_merge_slots(
                store_id, collected_slots, extracted_slots
            )

        # "لا بدي X بس" -> the cart becomes ONLY the product(s) named in this message
        if is_exclusive_selection(user_message):
            merged_slots = self._apply_exclusive_selection(store_id, user_message, merged_slots)

        # Check missing required slots
        missing = [slot for slot in REQUIRED_SLOTS if not merged_slots.get(slot)]

        if not missing and merged_slots.get("products"):
            # All slots are present and valid -> Jump to AWAITING_CONFIRMATION!
            return (
                ConversationState.AWAITING_CONFIRMATION,
                merged_slots,
                "All slots complete, awaiting customer confirmation",
            )

        if merged_slots.get("products"):
            # Some slots are missing -> COLLECTING_DETAILS
            return (
                ConversationState.COLLECTING_DETAILS,
                merged_slots,
                f"Missing slots: {', '.join(missing)}",
            )

        # No products selected yet
        if current_state in (ConversationState.DISCOVERY, ConversationState.PRODUCT_SELECTION):
            return (
                ConversationState.PRODUCT_SELECTION,
                merged_slots,
                "Browsing catalog or asking questions",
            )

        return current_state, merged_slots, "Continuing conversation"

    def _apply_exclusive_selection(
        self, store_id: str, user_message: str, slots: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Replace the cart with only the catalog products named in the message.

        Keeps the quantity already in the cart for a named product, defaults to 1
        for a newly named one. If no product is named ("لا بس واحد"), the cart is
        left as-is so quantity-only corrections still work.
        """
        msg_tokens = set(_tokens(normalize_arabic_text(user_message)))
        catalog = self.product_repo.get_active_catalog(store_id) or []
        named = [
            p for p in catalog
            if msg_tokens & _product_name_tokens(p)
        ]
        if not named:
            return slots

        current_by_id = {p.get("product_id"): p for p in slots.get("products") or []}
        products = []
        for prod in named:
            existing = current_by_id.get(prod["id"])
            products.append(existing or {
                "product_id": prod["id"],
                "product_name": prod["name_ar"],
                "unit_price_jod": float(prod["price_jod"]),
                "quantity": 1,
            })

        updated = dict(slots)
        updated["products"] = products
        return updated

    def finalize_order(
        self,
        store_id: str,
        conversation_id: str,
        customer_id: str | None,
        collected_slots: dict[str, Any],
        is_test: bool = False,
    ) -> dict[str, Any]:
        """
        Execute confirmed order (is_test marks dashboard-simulator orders):
        1. Final stock verification
        2. Insert into orders and order_items
        3. Update customer record
        4. Return confirmed order dict
        """
        products = collected_slots.get("products", [])
        if not products:
            raise ValueError("لا توجد منتجات في الطلب")

        # Re-verify the products are still offered before final confirmation
        for p in products:
            p_id = p.get("product_id")
            if p_id:
                avail, msg = self.product_service.check_available(store_id, p_id)
                if not avail:
                    raise ValueError(f"تعذر إتمام الطلب: {msg}")

        # Calculate final pricing
        price_summary = self.calculate_price_summary(store_id, collected_slots)
        if not price_summary:
            raise ValueError("خطأ في حساب المجموع")

        # Create order record
        order_data = {
            "customer_id": customer_id,
            "conversation_id": conversation_id,
            "status": OrderStatus.CONFIRMED.value,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
            "customer_name": collected_slots.get("customer_name"),
            "customer_phone": collected_slots.get("customer_phone"),
            "governorate": collected_slots.get("governorate"),
            "address_detail": collected_slots.get("address_detail"),
            "subtotal_jod": price_summary.subtotal_jod,
            "delivery_fee_jod": price_summary.delivery_fee_jod,
            "total_jod": price_summary.total_jod,
            "notes": collected_slots.get("notes"),
            "is_test": is_test,
        }

        items_data = [
            {
                "product_id": p.get("product_id"),
                "product_name_snapshot": p.get("product_name"),
                "unit_price_snapshot": p.get("unit_price_jod"),
                "quantity": p.get("quantity"),
                "line_total_jod": float(p["unit_price_jod"]) * int(p["quantity"]),
            }
            for p in products
        ]

        created_order = self.order_repo.create_order(store_id, order_data, items_data)

        # Update customer stats
        if customer_id:
            self.customer_repo.record_order_placed(
                store_id=store_id,
                customer_id=customer_id,
                name=collected_slots.get("customer_name"),
                phone_normalized=collected_slots.get("customer_phone"),
                governorate=collected_slots.get("governorate"),
                address_detail=collected_slots.get("address_detail"),
            )

        return created_order
