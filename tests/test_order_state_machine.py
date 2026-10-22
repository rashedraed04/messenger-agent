"""
Unit tests for Order state machine and slot merging.
"""

from unittest.mock import MagicMock
import pytest
from app.models.conversation import ConversationState
from app.services.order_service import OrderService


@pytest.fixture
def mock_order_service():
    order_repo = MagicMock()
    product_repo = MagicMock()
    setting_repo = MagicMock()
    setting_repo.get_delivery_fee.return_value = 2.0
    conv_repo = MagicMock()
    customer_repo = MagicMock()

    # Sample product mock
    product_repo.get_by_id.return_value = {
        "id": "p1",
        "name_ar": "سوفاج ديور",
        "price_jod": 45.0,
        "stock_quantity": 10,
        "in_stock": True,
        "is_active": True,
    }
    product_repo.get_active_catalog.return_value = [
        {
            "id": "p1",
            "name_ar": "سوفاج ديور",
            "name_en": "Dior Sauvage",
            "price_jod": 45.0,
            "stock_quantity": 10,
            "in_stock": True,
            "is_active": True,
        }
    ]

    service = OrderService(
        order_repo=order_repo,
        product_repo=product_repo,
        setting_repo=setting_repo,
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
    )
    return service


def test_single_slot_extraction_stays_in_collecting(mock_order_service):
    # Customer provides only product
    new_slots = {"products": [{"name_match": "سوفاج", "quantity": 1}]}
    merged, missing = mock_order_service.validate_and_merge_slots("s1", {}, new_slots)

    assert len(merged["products"]) == 1
    assert "customer_name" in missing
    assert "customer_phone" in missing
    assert "governorate" in missing
    assert "address_detail" in missing

    state, _, _ = mock_order_service.process_state_transition(
        store_id="s1",
        current_state=ConversationState.DISCOVERY,
        collected_slots={},
        user_message="بدي عطر سوفاج",
        extracted_slots=new_slots,
    )
    assert state == ConversationState.COLLECTING_DETAILS


def test_all_in_one_message_jumps_to_awaiting_confirmation(mock_order_service):
    # Customer gives all details in one message
    all_slots = {
        "products": [{"name_match": "سوفاج", "quantity": 1}],
        "customer_name": "أحمد",
        "customer_phone": "٠٧٩١٢٣٤٥٦٧",
        "governorate": "عمان",
        "address_detail": "طبربور قرب مسجد التوحيد",
    }

    state, slots, action = mock_order_service.process_state_transition(
        store_id="s1",
        current_state=ConversationState.DISCOVERY,
        collected_slots={},
        user_message="مرحبا بدي علبة سوفاج لاسم احمد تلفون 0791234567 عمان طبربور",
        extracted_slots=all_slots,
    )

    assert state == ConversationState.AWAITING_CONFIRMATION
    assert slots["customer_name"] == "أحمد"
    assert slots["customer_phone"] == "0791234567"
    assert slots["governorate"] == "عمّان"
    assert slots["delivery_fee_jod"] == 2.0


def test_confirmation_transitions_to_confirmed(mock_order_service):
    existing_slots = {
        "products": [{"product_id": "p1", "product_name": "سوفاج", "unit_price_jod": 45.0, "quantity": 1}],
        "customer_name": "أحمد",
        "customer_phone": "0791234567",
        "governorate": "عمّان",
        "address_detail": "طبربور",
    }

    state, _, _ = mock_order_service.process_state_transition(
        store_id="s1",
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=existing_slots,
        user_message="نعم تمام اعتمد",
    )
    assert state == ConversationState.CONFIRMED


def test_cancellation_from_awaiting_confirmation(mock_order_service):
    existing_slots = {
        "products": [{"product_id": "p1", "product_name": "سوفاج", "unit_price_jod": 45.0, "quantity": 1}],
    }

    state, slots, _ = mock_order_service.process_state_transition(
        store_id="s1",
        current_state=ConversationState.AWAITING_CONFIRMATION,
        collected_slots=existing_slots,
        user_message="لا الغي الطلب بديش اياه",
    )
    assert state == ConversationState.CANCELLED
    assert slots == {}


def test_human_handoff_trigger(mock_order_service):
    state, _, note = mock_order_service.process_state_transition(
        store_id="s1",
        current_state=ConversationState.PRODUCT_SELECTION,
        collected_slots={},
        user_message="بدي احكي مع انسان لو سمحت",
    )
    assert state == ConversationState.HUMAN_HANDOFF
    assert "human" in note.lower()
