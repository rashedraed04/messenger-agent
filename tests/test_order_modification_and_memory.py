"""
Regression tests for:
- BUG 1: "لا بدي سوفاج بس" (order modification) was falsely cancelling the order.
- BUG 2: a bare "مرحبا" was answered with an unprompted Invictus pitch because
  the prompt history held the OLDEST messages instead of the last 12 hours.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.ai.gemini_provider import build_chat_turns
from app.ai.provider_interface import AIProvider, AIResponse
from app.db.repositories.conversations import ConversationRepository
from app.models.conversation import ConversationState
from app.services.conversation_service import (
    CANCEL_REPLY,
    FRESH_GREETING_REPLY,
    ConversationService,
    is_pure_greeting,
)
from app.services.order_service import OrderService, is_cancellation_request

STORE_ID = "s1"

SAUVAGE = {
    "id": "p-sauvage",
    "name_ar": "سوفاج ديور",
    "name_en": "Dior Sauvage",
    "price_jod": 45.0,
    "stock_quantity": 10,
    "in_stock": True,
    "is_active": True,
}
INVICTUS = {
    "id": "p-invictus",
    "name_ar": "انفكتوس",
    "name_en": "Paco Rabanne Invictus",
    "price_jod": 30.0,
    "stock_quantity": 10,
    "in_stock": True,
    "is_active": True,
}
CATALOG = [SAUVAGE, INVICTUS]


def _cart_line(prod: dict, qty: int = 1) -> dict:
    return {
        "product_id": prod["id"],
        "product_name": prod["name_ar"],
        "unit_price_jod": prod["price_jod"],
        "quantity": qty,
    }


TWO_PERFUME_SLOTS = {
    "products": [_cart_line(INVICTUS), _cart_line(SAUVAGE)],
    "customer_name": "أحمد",
    "customer_phone": "0791234567",
    "governorate": "عمّان",
    "delivery_fee_jod": 2.0,
    "address_detail": "طبربور قرب مسجد التوحيد",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repos():
    product_repo = MagicMock()
    product_repo.get_active_catalog.return_value = CATALOG
    product_repo.get_by_id.side_effect = lambda _s, pid: next(
        (p for p in CATALOG if p["id"] == pid), None
    )

    conv_repo = MagicMock()
    conv_repo.get_recent_messages.return_value = []

    customer_repo = MagicMock()
    customer_repo.get_or_create.return_value = {"id": "cust-1"}

    faq_repo = MagicMock()
    faq_repo.list_active.return_value = []

    setting_repo = MagicMock()
    setting_repo.get_bot_config.return_value = {"bot_enabled": True, "store_name": "متجر العطور"}
    setting_repo.get_delivery_fee.return_value = 2.0

    return {
        "product": product_repo,
        "conv": conv_repo,
        "customer": customer_repo,
        "faq": faq_repo,
        "setting": setting_repo,
        "order": MagicMock(),
    }


@pytest.fixture
def order_service(repos):
    return OrderService(
        order_repo=repos["order"],
        product_repo=repos["product"],
        setting_repo=repos["setting"],
        conversation_repo=repos["conv"],
        customer_repo=repos["customer"],
    )


class FakeAI(AIProvider):
    """Records what the model was given and returns a canned response."""

    def __init__(self, response: AIResponse):
        self.response = response
        self.calls: list[dict] = []

    async def generate_response(self, system_instruction, user_message, conversation_history=None, timeout_seconds=10.0, images=None):
        self.calls.append({
            "system_instruction": system_instruction,
            "user_message": user_message,
            "conversation_history": conversation_history,
            "images": images,
        })
        return self.response


def _make_service(repos, order_service, ai_response: AIResponse):
    ai = FakeAI(ai_response)
    service = ConversationService(
        conversation_repo=repos["conv"],
        customer_repo=repos["customer"],
        product_repo=repos["product"],
        faq_repo=repos["faq"],
        setting_repo=repos["setting"],
        order_service=order_service,
        ai_provider=ai,
    )
    return service, ai


def _conversation(state: ConversationState, slots: dict, last_message_at: datetime) -> dict:
    return {
        "id": "conv-1",
        "state": state.value,
        "collected_slots": slots,
        "is_human_handoff": False,
        "last_message_at": last_message_at.isoformat(),
    }


def _final_update_state(conv_repo: MagicMock) -> dict:
    """kwargs of the last conversation_repo.update_state call."""
    return conv_repo.update_state.call_args.kwargs


# ---------------------------------------------------------------------------
# BUG 1 — unit: state machine
# ---------------------------------------------------------------------------


def test_la_badi_sauvage_bas_replaces_cart_instead_of_cancelling(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=TWO_PERFUME_SLOTS,
        user_message="لا بدي سوفاج بس",
        extracted_slots={"products": [{"name_match": "سوفاج", "quantity": 1}]},
        intent="place_order",
    )
    assert state == ConversationState.AWAITING_CONFIRMATION
    assert [p["product_id"] for p in slots["products"]] == [SAUVAGE["id"]]
    assert slots["customer_name"] == "أحمد"  # other details kept


def test_bas_keeps_only_named_product_even_if_ai_echoes_whole_cart(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=TWO_PERFUME_SLOTS,
        user_message="لا بدي سوفاج بس",
        extracted_slots={"products": [
            {"name_match": "انفكتوس", "quantity": 1},
            {"name_match": "سوفاج", "quantity": 1},
        ]},
        intent="modify_order",
    )
    assert state == ConversationState.AWAITING_CONFIRMATION
    assert [p["product_id"] for p in slots["products"]] == [SAUVAGE["id"]]


def test_bas_works_even_if_ai_extracts_no_products(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=TWO_PERFUME_SLOTS,
        user_message="لا بدي سوفاج بس",
        extracted_slots={},
        intent="general_inquiry",
    )
    assert state == ConversationState.AWAITING_CONFIRMATION
    assert [p["product_id"] for p in slots["products"]] == [SAUVAGE["id"]]


def test_quantity_correction_with_bas_is_not_cancellation(order_service):
    slots_two_units = {**TWO_PERFUME_SLOTS, "products": [_cart_line(SAUVAGE, qty=2)]}
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=slots_two_units,
        user_message="لا بس واحد",
        extracted_slots={"products": [{"name_match": "سوفاج", "quantity": 1}]},
        intent="modify_order",
    )
    assert state == ConversationState.AWAITING_CONFIRMATION
    assert slots["products"][0]["quantity"] == 1


def test_governorate_correction_is_not_cancellation(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.COLLECTING_DETAILS,
        collected_slots={"products": [_cart_line(SAUVAGE)]},
        user_message="لا خليها لعمان",
        extracted_slots={"governorate": "عمان"},
        intent="place_order",
    )
    assert state == ConversationState.COLLECTING_DETAILS
    assert slots["governorate"] == "عمّان"


def test_explicit_cancel_phrase_cancels(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=TWO_PERFUME_SLOTS,
        user_message="لا خلص كنسل الطلب",
        extracted_slots={},
        intent="cancel_order",
    )
    assert state == ConversationState.CANCELLED
    assert slots == {}


def test_affirmative_with_change_request_does_not_confirm_old_cart(order_service):
    state, slots, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=TWO_PERFUME_SLOTS,
        user_message="اه بس بدي سوفاج بس",
        extracted_slots={"products": [{"name_match": "سوفاج", "quantity": 1}]},
        intent="modify_order",
    )
    assert state == ConversationState.AWAITING_CONFIRMATION
    assert [p["product_id"] for p in slots["products"]] == [SAUVAGE["id"]]


@pytest.mark.parametrize(
    "message, extracted, intent, expected",
    [
        # modifications — never cancel
        ("لا بدي سوفاج بس", {"products": [{"name_match": "سوفاج"}]}, "place_order", False),
        ("لا بدي سوفاج بس", {}, "place_order", False),
        ("لا بس واحد", {"products": [{"name_match": "سوفاج", "quantity": 1}]}, "modify_order", False),
        ("لا خليها لعمان", {"governorate": "عمان"}, "place_order", False),
        ("الغي الانفكتوس وخليها سوفاج", {"products": [{"name_match": "سوفاج"}]}, "modify_order", False),
        # explicit cancellations
        ("لا خلص كنسل الطلب", {}, "cancel_order", True),
        ("لا خلص كنسل الطلب", {}, "general_inquiry", True),
        ("إلغاء", {}, None, True),
        ("ما بدي أطلب", {}, None, True),
        ("لا خلص بطلت", {}, None, True),
        ("كنسل الطلب", {"products": [{"name_match": "سوفاج"}]}, "cancel_order", True),
        # bare refusals
        ("لا", {}, None, True),
        ("لأ", {}, None, True),
        ("لا شكراً", {}, None, True),
        # AI says cancel but the message carries a replacement -> modification
        ("لا بدي سوفاج", {"products": [{"name_match": "سوفاج"}]}, "cancel_order", False),
    ],
)
def test_is_cancellation_request(message, extracted, intent, expected):
    assert is_cancellation_request(message, extracted, intent) is expected


# ---------------------------------------------------------------------------
# BUG 1 — integration: full conversation turn
# ---------------------------------------------------------------------------


async def test_turn_modify_order_returns_updated_sauvage_summary(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.AWAITING_CONFIRMATION, dict(TWO_PERFUME_SLOTS), now - timedelta(minutes=5)
    )
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="تمام، عدلنا الطلب ليصير سوفاج بس",
        extracted_slots={"products": [{"name_match": "سوفاج", "quantity": 1}]},
        intent="place_order",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "لا بدي سوفاج بس")

    assert len(replies) == 1
    assert "إلغاء" not in replies[0]
    assert "سوفاج" in replies[0]
    assert "انفكتوس" not in replies[0]
    update = _final_update_state(repos["conv"])
    assert update["state"] == ConversationState.AWAITING_CONFIRMATION
    assert [p["product_id"] for p in update["collected_slots"]["products"]] == [SAUVAGE["id"]]


async def test_turn_explicit_cancel_transitions_to_cancelled(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.AWAITING_CONFIRMATION, dict(TWO_PERFUME_SLOTS), now - timedelta(minutes=5)
    )
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="تم", intent="cancel_order",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "لا خلص كنسل الطلب")

    assert "لغيتلك الطلب" in replies[0]
    assert "بناءً على رغبتك" not in replies[0]
    update = _final_update_state(repos["conv"])
    assert update["state"] == ConversationState.CANCELLED
    assert update["collected_slots"] == {}


# ---------------------------------------------------------------------------
# BUG 2 — greetings and 12-hour memory
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["مرحبا", "السلام عليكم", "مساء الخير", "هلا", "هلا والله!", "Hi"])
def test_is_pure_greeting_true(text):
    assert is_pure_greeting(text)


@pytest.mark.parametrize("text", ["مرحبا بدي سوفاج", "كم سعر انفكتوس", "لا بدي سوفاج بس", ""])
def test_is_pure_greeting_false(text):
    assert not is_pure_greeting(text)


async def test_fresh_customer_greeting_never_mentions_unasked_product(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(ConversationState.DISCOVERY, {}, now)
    # Simulate exactly the hallucination from production
    service, ai = _make_service(repos, order_service, AIResponse(
        response_text="يا هلا بك! نعم عطر انفكتوس (100 مل) متوفر عنا وأصلي 100% وسعره 30 دينار. بتحب تطلب منه؟",
        intent="general_inquiry",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-new", "مرحبا")

    assert replies == [FRESH_GREETING_REPLY]
    assert "انفكتوس" not in replies[0]
    call = ai.calls[0]
    assert call["conversation_history"] == []
    assert "زبون جديد" in call["system_instruction"]
    assert "انفكتوس" not in call["system_instruction"].split("# كتالوج")[0]


async def test_fresh_customer_good_greeting_passes_through(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(ConversationState.DISCOVERY, {}, now)
    natural = "هلا والله، نورتنا 🌸 شو بتدور عليه اليوم؟"
    service, _ = _make_service(repos, order_service, AIResponse(response_text=natural, intent="greeting"))

    replies = await service.handle_customer_message(STORE_ID, "psid-new", "مرحبا")

    assert replies == [natural]


async def test_returning_customer_within_12h_gets_contextual_memory(repos, order_service):
    now = datetime.now(timezone.utc)
    cart = {"products": [_cart_line(SAUVAGE)]}
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.COLLECTING_DETAILS, cart, now - timedelta(hours=3)
    )
    repos["conv"].get_recent_messages.return_value = [
        {"direction": "inbound", "content": "بدي سوفاج", "created_at": (now - timedelta(hours=3, minutes=2)).isoformat()},
        {"direction": "outbound", "content": "أبشر! شو الاسم ورقم التلفون؟", "created_at": (now - timedelta(hours=3, minutes=1)).isoformat()},
    ]
    contextual = "هلا والله من جديد، كنا نحكي عن طلبك لـ سوفاج ديور، بتحب نكمل نثبت الطلب؟"
    service, ai = _make_service(repos, order_service, AIResponse(response_text=contextual, intent="greeting"))

    replies = await service.handle_customer_message(STORE_ID, "psid-ret", "مرحبا")

    # Memory query: last 12 hours, up to 20 messages, loaded before saving the new message
    kwargs = repos["conv"].get_recent_messages.call_args.kwargs
    assert kwargs["limit"] == 20
    assert abs((now - timedelta(hours=12)) - kwargs["since"]) < timedelta(minutes=1)

    call = ai.calls[0]
    assert call["conversation_history"] == [
        {"role": "user", "content": "بدي سوفاج"},
        {"role": "model", "content": "أبشر! شو الاسم ورقم التلفون؟"},
    ]
    assert "زبون عائد" in call["system_instruction"]
    assert "سوفاج ديور (كمية: 1)" in call["system_instruction"]
    # Cart product may be referenced in a greeting
    assert replies == [contextual]
    assert _final_update_state(repos["conv"])["collected_slots"]["products"][0]["product_id"] == SAUVAGE["id"]


async def test_returning_customer_after_12h_starts_fresh(repos, order_service):
    now = datetime.now(timezone.utc)
    stale_cart = {"products": [_cart_line(INVICTUS)], "customer_name": "أحمد"}
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.COLLECTING_DETAILS, stale_cart, now - timedelta(hours=13)
    )
    repos["conv"].get_recent_messages.return_value = []  # DB window filter excludes everything
    service, ai = _make_service(repos, order_service, AIResponse(
        response_text="يا هلا! بدك تكمل طلب انفكتوس؟", intent="greeting",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-old", "مرحبا")

    # First update_state call is the stale reset
    first_update = repos["conv"].update_state.call_args_list[0].kwargs
    assert first_update["state"] == ConversationState.DISCOVERY
    assert first_update["collected_slots"] == {}

    call = ai.calls[0]
    assert call["conversation_history"] == []
    assert "لم يتم جمع أي معلومات بعد" in call["system_instruction"]
    assert "زبون جديد" in call["system_instruction"]
    assert replies == [FRESH_GREETING_REPLY]
    assert _final_update_state(repos["conv"])["collected_slots"] == {}


async def test_greeting_after_cancelled_order_does_not_repeat_cancel_message(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.CANCELLED, {}, now - timedelta(minutes=10)
    )
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="يا هلا فيك! كيف بقدر أساعدك؟", intent="greeting",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "مرحبا")

    assert "إلغاء" not in replies[0]
    assert _final_update_state(repos["conv"])["state"] != ConversationState.CANCELLED


# ---------------------------------------------------------------------------
# Human-sounding replies
# ---------------------------------------------------------------------------

ROBOTIC_MARKERS = ("بناءً على رغبتك", "يا هلا بك!", "━━━━━━", "📱", "**", "!")


def _assert_human(text: str):
    for marker in ROBOTIC_MARKERS:
        assert marker not in text, f"robotic marker {marker!r} in {text!r}"


async def test_markdown_is_stripped_from_outgoing_reply(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(ConversationState.DISCOVERY, {}, now)
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="**اه موجود عنا سوفاج ديور!** ريحته بتجنن", intent="inquire_price",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "عندكم سوفاج؟")

    assert replies == ["اه موجود عنا سوفاج ديور ريحته بتجنن"]
    # What is stored is exactly what the customer sees
    outbound = repos["conv"].add_message.call_args_list[-1].kwargs
    assert outbound["content"] == replies[0]


async def test_robotic_ai_greeting_is_replaced_with_human_one(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(ConversationState.DISCOVERY, {}, now)
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="يا هلا بك! نعم عطر انفكتوس متوفر", intent="greeting",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-new", "مرحبا")

    _assert_human(replies[0])


async def test_cancellation_reply_sounds_human(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.AWAITING_CONFIRMATION, dict(TWO_PERFUME_SLOTS), now - timedelta(minutes=5)
    )
    service, _ = _make_service(repos, order_service, AIResponse(response_text="", intent="cancel_order"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "لا خلص بطلت")

    assert replies == [CANCEL_REPLY]
    _assert_human(replies[0])


async def test_order_summary_sounds_human_and_uses_python_prices(repos, order_service):
    now = datetime.now(timezone.utc)
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.AWAITING_CONFIRMATION, dict(TWO_PERFUME_SLOTS), now - timedelta(minutes=5)
    )
    service, _ = _make_service(repos, order_service, AIResponse(
        response_text="المجموع 999 دينار",  # AI-made price must never reach the customer
        extracted_slots={"products": [{"name_match": "سوفاج", "quantity": 2}]},
        intent="modify_order",
    ))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "بدي 2 سوفاج بس")

    summary = replies[0]
    _assert_human(summary)
    assert summary.startswith("تمام يا غالي، هيك تفاصيل طلبك جاهزة للتأكيد:")
    assert "- سوفاج ديور عدد 2 (90 دينار)" in summary
    assert "المجموع كامل: 92 دينار (الدفع عند الاستلام)" in summary
    assert "999" not in summary
    assert summary.endswith("أعتمدلك الطلب؟")


@pytest.mark.parametrize("text", ["اعتمده", "اه ثبته", "تمام"])
def test_natural_confirmations_confirm_the_order(order_service, text):
    next_state, _, _ = order_service.process_state_transition(
        store_id=STORE_ID,
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=dict(TWO_PERFUME_SLOTS),
        user_message=text,
        extracted_slots={},
        intent="confirm_order",
    )
    assert next_state == ConversationState.CONFIRMED


# ---------------------------------------------------------------------------
# History plumbing
# ---------------------------------------------------------------------------


def test_get_recent_messages_returns_latest_in_chronological_order():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value
    query.gte.return_value = query
    query.order.return_value.limit.return_value.execute.return_value.data = [
        {"content": "newest"}, {"content": "middle"}, {"content": "oldest"},
    ]
    since = datetime(2026, 10, 19, tzinfo=timezone.utc)

    msgs = ConversationRepository(client).get_recent_messages("conv-1", since=since, limit=20)

    assert [m["content"] for m in msgs] == ["oldest", "middle", "newest"]
    query.gte.assert_called_once_with("created_at", since.isoformat())
    query.order.assert_called_once_with("created_at", desc=True)
    query.order.return_value.limit.assert_called_once_with(20)


def test_build_chat_turns_alternates_roles():
    history = [
        {"role": "model", "content": "رسالة ترحيب قديمة"},  # leading model turn dropped
        {"role": "user", "content": "بدي سوفاج"},
        {"role": "model", "content": "أبشر"},
        {"role": "model", "content": "شو الاسم؟"},  # merged with previous
        {"role": "user", "content": ""},  # skipped
    ]
    turns = build_chat_turns(history, "مرحبا")
    assert turns == [
        ("user", "بدي سوفاج"),
        ("model", "أبشر\nشو الاسم؟"),
        ("user", "مرحبا"),
    ]


@pytest.mark.asyncio
async def test_disabled_bot_stays_silent(repos, order_service):
    """Bot switched off from the dashboard: no reply at all, no AI call, message still logged."""
    repos["setting"].get_bot_config.return_value = {
        "bot_enabled": False,
        "human_handoff_message": "تم تحويلك لخدمة العملاء",
    }
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.DISCOVERY, {}, datetime.now(timezone.utc)
    )
    service, ai = _make_service(repos, order_service, AIResponse(response_text="هلا"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "مرحبا")

    assert replies == []
    assert ai.calls == []
    repos["conv"].add_message.assert_called_once()
