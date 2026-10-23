"""
Unit and integration tests for Meta Messenger webhook handler.
"""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock

from app.messenger.webhook_handler import verify_hub_signature


def test_get_webhook_verification_success(client):
    res = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "1158201444",
        },
    )
    assert res.status_code == 200
    assert res.text == "1158201444"


def test_get_webhook_verification_failure(client):
    res = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "1158201444",
        },
    )
    assert res.status_code == 403


def test_verify_hub_signature():
    secret = "my_app_secret_123"
    payload = b'{"object":"page","entry":[]}'

    # Correct signature
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert verify_hub_signature(payload, f"sha256={sig}", secret) is True

    # Tampered payload
    tampered_payload = b'{"object":"page","entry":[{"tampered":true}]}'
    assert verify_hub_signature(tampered_payload, f"sha256={sig}", secret) is False

    # Bad signature header format
    assert verify_hub_signature(payload, "invalid_header", secret) is False
    assert verify_hub_signature(payload, None, secret) is False


def test_webhook_idempotency_deduplication():
    from app.messenger.webhook_handler import WebhookHandler

    mock_event_repo = MagicMock()
    # First call returns True (new), second call returns False (duplicate)
    mock_event_repo.mark_processed_if_new.side_effect = [True, False]

    mock_conv_service = MagicMock()
    mock_conv_service.handle_customer_message = AsyncMock(return_value=["يا هلا فيك!"])

    mock_send_api = MagicMock()
    mock_send_api.send_reply = AsyncMock()
    mock_send_api.send_typing_indicator = AsyncMock()

    handler = WebhookHandler(
        event_repo=mock_event_repo,
        conversation_service=mock_conv_service,
        send_api=mock_send_api,
    )

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page_123",
                "messaging": [
                    {
                        "sender": {"id": "user_456"},
                        "recipient": {"id": "page_123"},
                        "message": {"mid": "mid_repeat_1", "text": "مرحبا"},
                    }
                ],
            }
        ],
    }

    import asyncio

    # First delivery
    res1 = asyncio.run(handler.process_payload("s1", payload))
    assert len(res1) == 1
    assert res1[0]["status"] == "processed"
    assert mock_conv_service.handle_customer_message.call_count == 1
    mock_send_api.send_reply.assert_awaited_once_with("user_456", "يا هلا فيك!")

    # Second delivery with identical mid
    res2 = asyncio.run(handler.process_payload("s1", payload))
    assert len(res2) == 1
    assert res2[0]["status"] == "duplicate_skipped"
    # Call count should not have increased
    assert mock_conv_service.handle_customer_message.call_count == 1


def _single_message_payload(mid: str) -> dict:
    return {
        "object": "page",
        "entry": [{
            "id": "page_123",
            "messaging": [{
                "sender": {"id": "user_456"},
                "recipient": {"id": "page_123"},
                "message": {"mid": mid, "text": "مرحبا"},
            }],
        }],
    }


def _handler(bot_enabled: bool, replies: list[str]):
    from app.messenger.webhook_handler import WebhookHandler

    event_repo = MagicMock()
    event_repo.mark_processed_if_new.return_value = True
    conv_service = MagicMock()
    conv_service.is_bot_enabled.return_value = bot_enabled
    conv_service.handle_customer_message = AsyncMock(return_value=replies)
    send_api = MagicMock()
    send_api.send_reply = AsyncMock()
    send_api.send_typing_indicator = AsyncMock()
    return WebhookHandler(event_repo=event_repo, conversation_service=conv_service, send_api=send_api), send_api


def test_disabled_bot_shows_no_typing_indicator():
    import asyncio

    handler, send_api = _handler(bot_enabled=False, replies=[])
    asyncio.run(handler.process_payload("s1", _single_message_payload("mid_off")))

    send_api.send_typing_indicator.assert_not_awaited()
    send_api.send_reply.assert_not_awaited()


def test_typing_indicator_cleared_when_no_reply():
    """Bot on but chat handed to the owner: the dots must not stay on screen."""
    import asyncio

    handler, send_api = _handler(bot_enabled=True, replies=[])
    asyncio.run(handler.process_payload("s1", _single_message_payload("mid_handoff")))

    actions = [c.args[1] for c in send_api.send_typing_indicator.await_args_list]
    assert actions == ["typing_on", "typing_off"]
