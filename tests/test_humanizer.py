"""
Tests for human-sounding replies: text humanizer, persona prompt, canned
replies, and the Messenger typing delay.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.gemini_provider import GeminiProvider
from app.ai.prompt_builder import FORBIDDEN_PHRASES, build_system_prompt
from app.config import Settings
from app.messenger.send_api import MessengerSendAPI, human_typing_delay
from app.services import conversation_service
from app.services.text_humanizer import humanize_reply

ROBOTIC_MARKERS = ("بناءً على رغبتك", "يا هلا بك!", "━━━━━━", "📱", "**", "!")


# ---------------------------------------------------------------------------
# humanize_reply
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**سوفاج** متوفر عنا", "سوفاج متوفر عنا"),
        ("# العطور\n*انفكتوس* فخم ومرتب", "العطور\nانفكتوس فخم ومرتب"),
        ("هلا والله!! نورتنا!", "هلا والله نورتنا"),
        ("ملخص\n━━━━━━━━━━\nسوفاج\n----------", "ملخص\nسوفاج"),
        ("📱 الاسم: أحمد\n📞 الهاتف: 0791234567", "الاسم: أحمد\nالهاتف: 0791234567"),
        ("يا هلا بك، نعم متوفر", "يا هلا فيك، اه متوفر"),
        ("عذراً، تم إلغاء الطلب بناءً على رغبتك", "معلش، تم إلغاء الطلب متل ما بدك"),
        ("حسناً، هل ترغب بطلبه؟", "تمام، بتحب بطلبه؟"),
    ],
)
def test_humanize_reply(raw, expected):
    assert humanize_reply(raw) == expected


def test_humanize_reply_leaves_lookalike_words_alone():
    # "بك" / "نعم" only as whole words
    assert humanize_reply("بكرة بوصلك، ونعمان استلم") == "بكرة بوصلك، ونعمان استلم"


def test_humanize_reply_keeps_order_summary_lines():
    summary = "- سوفاج ديور عدد 1 (45 دينار)\nالاسم: أحمد - الرقم: 0791234567"
    assert humanize_reply(summary) == summary


def test_humanize_reply_empty():
    assert humanize_reply("") == ""


# ---------------------------------------------------------------------------
# Canned replies and persona prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        conversation_service.FRESH_GREETING_REPLY,
        conversation_service.CANCEL_REPLY,
        conversation_service.HANDOFF_REPLY,
        conversation_service.FINALIZE_ERROR_REPLY,
    ],
)
def test_canned_replies_have_no_robotic_phrasing(reply):
    for marker in ROBOTIC_MARKERS:
        assert marker not in reply
    assert humanize_reply(reply) == reply


def _prompt() -> str:
    return build_system_prompt(
        bot_config={"store_name": "متجر العطور", "delivery_fee_jod": 2.5},
        catalog=[{"name_ar": "سوفاج ديور", "size_ml": 100, "price_jod": 45, "in_stock": True}],
        faqs=[],
        current_state="DISCOVERY",
        collected_slots={},
    )


def test_prompt_sets_jordanian_salesperson_persona():
    prompt = _prompt()
    assert "موظف المبيعات" in prompt
    assert "بعمّان" in prompt
    assert "المساعد الذكي" not in prompt
    for phrase in FORBIDDEN_PHRASES:
        assert f'"{phrase}"' in prompt


def test_prompt_marks_style_examples_as_not_live_chat():
    prompt = _prompt()
    start, end = prompt.index("<<<بداية_الأمثلة>>>"), prompt.index("<<<نهاية_الأمثلة>>>")
    assert start < end
    assert "مش جزء من المحادثة الحالية" in prompt[:start]
    assert "لا خلص بطلت" in prompt[start:end]


def test_prompt_prices_written_like_chat():
    prompt = _prompt()
    assert "السعر: 45 دينار" in prompt
    assert "ثابتة 2.5 دينار" in prompt


def test_no_lite_models_in_fallback_chain():
    provider = GeminiProvider(api_key="")
    assert not any("lite" in m for m in [provider.model_name, *provider.fallback_models])


# ---------------------------------------------------------------------------
# Typing delay
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("length", "expected"),
    [(0, 1.5), (10, 1.5), (80, 2.4), (500, 3.5)],
)
def test_human_typing_delay_bounds(length, expected):
    assert human_typing_delay("x" * length) == pytest.approx(expected)


async def test_send_reply_types_then_pauses_then_sends():
    api = MessengerSendAPI(page_access_token="test-token", typing_delay_enabled=True)
    api._post_payload = AsyncMock(return_value={})
    with patch("app.messenger.send_api.asyncio.sleep", new=AsyncMock()) as sleep:
        await api.send_reply("psid-1", "هلا والله")

    sleep.assert_awaited_once_with(1.5)
    payloads = [c.args[0] for c in api._post_payload.await_args_list]
    assert payloads[0] == {"recipient": {"id": "psid-1"}, "sender_action": "typing_on"}
    assert payloads[1]["message"] == {"text": "هلا والله"}


async def test_send_reply_without_delay_sends_immediately():
    api = MessengerSendAPI(page_access_token="test-token", typing_delay_enabled=False)
    api._post_payload = AsyncMock(return_value={})
    with patch("app.messenger.send_api.asyncio.sleep", new=AsyncMock()) as sleep:
        await api.send_reply("psid-1", "هلا والله")

    sleep.assert_not_awaited()
    assert api._post_payload.await_count == 1


async def test_send_reply_still_sends_if_typing_indicator_fails():
    api = MessengerSendAPI(page_access_token="test-token", typing_delay_enabled=True)
    api.send_typing_indicator = AsyncMock(side_effect=RuntimeError("meta down"))
    api.send_text_message = AsyncMock(return_value={})
    with patch("app.messenger.send_api.asyncio.sleep", new=AsyncMock()):
        await api.send_reply("psid-1", "هلا")

    api.send_text_message.assert_awaited_once_with("psid-1", "هلا")


def test_typing_delay_disabled_under_pytest():
    assert Settings(enable_typing_delay=True).enable_typing_delay is False
