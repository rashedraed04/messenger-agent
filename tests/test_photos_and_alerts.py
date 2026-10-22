"""
Tests for customer photos (product recognition) and angry-customer Telegram alerts.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.provider_interface import AIResponse, ImageInput
from app.ai.response_parser import parse_ai_response
from app.messenger.webhook_handler import WebhookHandler, extract_image_urls
from app.messenger.message_types import IncomingMessage
from app.models.conversation import ConversationState
from app.services.conversation_service import (
    CUSTOMER_PHOTO_LABEL,
    PHOTO_MARKER,
    PHOTO_ONLY_PROMPT,
    ConversationService,
)
from app.services.images import _url_allowed, MESSENGER_IMAGE_HOSTS
from tests.test_order_modification_and_memory import (  # noqa: F401 (fixtures)
    STORE_ID,
    FakeAI,
    _conversation,
    order_service,
    repos,
)

PHOTO = ImageInput(data=b"\xff\xd8fake-jpeg", mime_type="image/jpeg", source_url="https://scontent.xx.fbcdn.net/p.jpg")


def _service(repos, order_service, response: AIResponse, notifier=None, catalog_fetcher=None):
    ai = FakeAI(response)
    service = ConversationService(
        conversation_repo=repos["conv"],
        customer_repo=repos["customer"],
        product_repo=repos["product"],
        faq_repo=repos["faq"],
        setting_repo=repos["setting"],
        order_service=order_service,
        ai_provider=ai,
        alert_notifier=notifier,
        catalog_image_fetcher=catalog_fetcher or AsyncMock(return_value=None),
    )
    return service, ai


@pytest.fixture
def fresh(repos):
    repos["conv"].get_or_create.return_value = _conversation(
        ConversationState.DISCOVERY, {}, datetime.now(timezone.utc)
    )
    return repos


# ---------------------------------------------------------------------------
# Photos
# ---------------------------------------------------------------------------
async def test_photo_only_message_is_sent_to_model_with_label(fresh, order_service):
    service, ai = _service(fresh, order_service, AIResponse(response_text="هاي سجادة الصلاة المخمل، سعرها 15 دينار"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "", images=[PHOTO])

    assert replies == ["هاي سجادة الصلاة المخمل، سعرها 15 دينار"]
    call = ai.calls[0]
    assert call["user_message"] == PHOTO_ONLY_PROMPT
    assert [img.label for img in call["images"]] == [CUSTOMER_PHOTO_LABEL]
    inbound = fresh["conv"].add_message.call_args_list[0].kwargs
    assert inbound["content"] == PHOTO_MARKER
    assert inbound["message_type"] == "image"
    assert inbound["ai_metadata"] == {"image_urls": [PHOTO.source_url]}


async def test_catalog_photos_go_before_customer_photo(fresh, order_service):
    fresh["product"].get_active_catalog.return_value = [
        {"id": "p1", "name_ar": "مسبحة كهرمان", "price_jod": 10, "in_stock": True, "image_url": "https://cdn.example/a.jpg"},
        {"id": "p2", "name_ar": "مصحف", "price_jod": 8, "in_stock": True, "image_url": ""},
    ]
    catalog_photo = ImageInput(data=b"x", mime_type="image/png")
    fetcher = AsyncMock(return_value=catalog_photo)
    service, ai = _service(fresh, order_service, AIResponse(response_text="هاي مسبحة الكهرمان"), catalog_fetcher=fetcher)

    await service.handle_customer_message(STORE_ID, "psid-1", "بكم هاي؟", images=[PHOTO])

    fetcher.assert_awaited_once_with("https://cdn.example/a.jpg")
    labels = [img.label for img in ai.calls[0]["images"]]
    assert labels == ["صورة من الكتالوج: مسبحة كهرمان", CUSTOMER_PHOTO_LABEL]
    assert ai.calls[0]["user_message"] == "بكم هاي؟"


async def test_text_message_sends_no_images(fresh, order_service):
    fetcher = AsyncMock()
    service, ai = _service(fresh, order_service, AIResponse(response_text="هلا"), catalog_fetcher=fetcher)

    await service.handle_customer_message(STORE_ID, "psid-1", "عندكم مصاحف؟")

    assert ai.calls[0]["images"] is None
    fetcher.assert_not_awaited()


async def test_unreadable_photo_asks_customer_without_calling_model(fresh, order_service):
    service, ai = _service(fresh, order_service, AIResponse(response_text="لازم ما ينبعت"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "", images=[], unreadable_images=1)

    assert len(replies) == 1 and "الصورة" in replies[0]
    assert ai.calls == []


async def test_photo_with_greeting_is_not_replaced_by_greeting_guard(fresh, order_service):
    fresh["product"].get_active_catalog.return_value = [
        {"id": "p1", "name_ar": "سجادة صلاة مخمل", "price_jod": 15, "in_stock": True},
    ]
    reply = "هلا والله، هاي سجادة صلاة مخمل وسعرها 15 دينار"
    service, _ = _service(fresh, order_service, AIResponse(response_text=reply))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "مرحبا", images=[PHOTO])

    assert replies == [reply]


def test_extract_image_urls_skips_stickers_and_other_attachments():
    message = IncomingMessage(mid="m1", attachments=[
        {"type": "image", "payload": {"url": "https://scontent.fbcdn.net/1.jpg"}},
        {"type": "image", "payload": {"url": "https://scontent.fbcdn.net/like.png", "sticker_id": 369239263222822}},
        {"type": "audio", "payload": {"url": "https://cdn.fbsbx.com/a.mp4"}},
    ])
    assert extract_image_urls(message) == ["https://scontent.fbcdn.net/1.jpg"]


@pytest.mark.parametrize("url, allowed", [
    ("https://scontent.xx.fbcdn.net/v/t1.jpg", True),
    ("https://cdn.fbsbx.com/v/t59.jpg", True),
    ("http://scontent.xx.fbcdn.net/v/t1.jpg", False),
    ("https://evil.example/fbcdn.net.jpg", False),
    ("https://fbcdn.net.evil.example/x.jpg", False),
])
def test_messenger_image_host_allowlist(url, allowed):
    assert _url_allowed(url, MESSENGER_IMAGE_HOSTS) is allowed


async def test_webhook_photo_message_is_processed():
    event_repo = MagicMock()
    event_repo.mark_processed_if_new.return_value = True
    conv_service = MagicMock()
    conv_service.handle_customer_message = AsyncMock(return_value=["هاي مسبحة"])
    send_api = MagicMock(send_reply=AsyncMock(), send_typing_indicator=AsyncMock())
    fetcher = AsyncMock(side_effect=[PHOTO, None])
    handler = WebhookHandler(event_repo, conv_service, send_api, image_fetcher=fetcher)

    payload = {"object": "page", "entry": [{"id": "page", "messaging": [{
        "sender": {"id": "u1"}, "recipient": {"id": "page"},
        "message": {"mid": "m1", "attachments": [
            {"type": "image", "payload": {"url": "https://scontent.fbcdn.net/1.jpg"}},
            {"type": "image", "payload": {"url": "https://scontent.fbcdn.net/2.jpg"}},
        ]},
    }]}]}
    results = await handler.process_payload(STORE_ID, payload)

    assert results[0]["status"] == "processed"
    kwargs = conv_service.handle_customer_message.call_args.kwargs
    assert kwargs["user_text"] == ""
    assert kwargs["images"] == [PHOTO]
    assert kwargs["unreadable_images"] == 1
    send_api.send_reply.assert_awaited_once_with("u1", "هاي مسبحة")


# ---------------------------------------------------------------------------
# Angry customer alerts
# ---------------------------------------------------------------------------
def test_parser_reads_customer_mood():
    assert parse_ai_response('{"response_text": "x", "customer_mood": "angry"}').customer_angry is True
    assert parse_ai_response('{"response_text": "x", "customer_mood": "normal"}').customer_angry is False
    assert parse_ai_response('{"response_text": "x"}').customer_angry is False


async def test_angry_customer_triggers_one_telegram_alert(fresh, order_service):
    fresh["customer"].get_or_create.return_value = {"id": "cust-1", "name": "أبو أحمد"}
    notifier = MagicMock(send_message=AsyncMock(return_value=True))
    response = AIResponse(response_text="حقك علينا، بلّغت صاحب المحل", customer_angry=True)
    service, _ = _service(fresh, order_service, response, notifier=notifier)

    await service.handle_customer_message(STORE_ID, "psid-1", "صرلي أسبوع بستنى الطلب!!")

    notifier.send_message.assert_awaited_once()
    alert = notifier.send_message.call_args.args[0]
    assert "أبو أحمد" in alert and "صرلي أسبوع بستنى الطلب" in alert
    assert "business.facebook.com/latest/inbox" in alert
    outbound_meta = fresh["conv"].add_message.call_args_list[-1].kwargs["ai_metadata"]
    assert outbound_meta["customer_mood"] == "angry" and outbound_meta["angry_alert"] is True


async def test_no_second_alert_within_memory_window(fresh, order_service):
    fresh["conv"].get_recent_messages.return_value = [
        {"direction": "outbound", "content": "حقك علينا", "ai_metadata": {"angry_alert": True}},
    ]
    notifier = MagicMock(send_message=AsyncMock(return_value=True))
    service, _ = _service(fresh, order_service, AIResponse(response_text="حقك علينا", customer_angry=True), notifier=notifier)

    await service.handle_customer_message(STORE_ID, "psid-1", "لسا ما حدا حكاني!")

    notifier.send_message.assert_not_awaited()


async def test_calm_customer_sends_no_alert(fresh, order_service):
    notifier = MagicMock(send_message=AsyncMock(return_value=True))
    service, _ = _service(fresh, order_service, AIResponse(response_text="أبشر"), notifier=notifier)

    await service.handle_customer_message(STORE_ID, "psid-1", "بكم المسبحة؟")

    notifier.send_message.assert_not_awaited()


async def test_telegram_failure_does_not_break_reply(fresh, order_service):
    notifier = MagicMock(send_message=AsyncMock(side_effect=RuntimeError("telegram down")))
    service, _ = _service(fresh, order_service, AIResponse(response_text="حقك علينا", customer_angry=True), notifier=notifier)

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "خدمة زفت")

    assert replies == ["حقك علينا"]


async def test_simulator_alert_is_marked_as_test(fresh, order_service):
    notifier = MagicMock(send_message=AsyncMock(return_value=True))
    service, _ = _service(fresh, order_service, AIResponse(response_text="حقك علينا", customer_angry=True), notifier=notifier)

    await service.handle_customer_message(STORE_ID, "sim_admin_1_abc", "خدمة زفت")

    assert "تجربة" in notifier.send_message.call_args.args[0]


# ---------------------------------------------------------------------------
# Handoff resumes after the memory window
# ---------------------------------------------------------------------------
async def test_handoff_resumes_after_12_quiet_hours(repos, order_service):
    conv = _conversation(ConversationState.HUMAN_HANDOFF, {}, datetime.now(timezone.utc) - timedelta(hours=13))
    conv["is_human_handoff"] = True
    repos["conv"].get_or_create.return_value = conv
    service, ai = _service(repos, order_service, AIResponse(response_text="هلا والله، كيف بقدر أساعدك؟"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "مرحبا")

    assert replies == ["هلا والله، كيف بقدر أساعدك؟"]
    repos["conv"].set_human_handoff.assert_any_call(
        STORE_ID, "conv-1", is_handoff=False, reason="Resumed after 12 quiet hours"
    )


async def test_recent_handoff_keeps_bot_silent(repos, order_service):
    conv = _conversation(ConversationState.HUMAN_HANDOFF, {}, datetime.now(timezone.utc) - timedelta(hours=2))
    conv["is_human_handoff"] = True
    repos["conv"].get_or_create.return_value = conv
    service, ai = _service(repos, order_service, AIResponse(response_text="لازم ما ينبعت"))

    replies = await service.handle_customer_message(STORE_ID, "psid-1", "وينكم؟")

    assert replies == [] and ai.calls == []
