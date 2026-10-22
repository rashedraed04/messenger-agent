"""
Unit and integration tests for Meta Messenger webhook handler.
"""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
import pytest

from app.main import app
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
