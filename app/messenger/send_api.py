"""
Meta Messenger Send API client.
"""

import asyncio
import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v21.0/me/messages"

# Human typing pause bounds (seconds); the cap keeps us well inside Cloud Run's budget
TYPING_SECONDS_PER_CHAR = 0.03
MIN_TYPING_DELAY = 1.5
MAX_TYPING_DELAY = 3.5


def human_typing_delay(text: str) -> float:
    """Seconds a person would plausibly spend typing this reply."""
    return min(max(len(text) * TYPING_SECONDS_PER_CHAR, MIN_TYPING_DELAY), MAX_TYPING_DELAY)


class MessengerSendAPI:
    """Client for dispatching outbound messages to Facebook Messenger."""

    def __init__(self, page_access_token: str, typing_delay_enabled: bool = False):
        self.page_access_token = page_access_token
        self.typing_delay_enabled = typing_delay_enabled

    async def _post_payload(self, payload: dict[str, Any], timeout: float = 4.0) -> dict[str, Any]:
        """Send JSON payload to Meta Graph API."""
        if not self.page_access_token or self.page_access_token.startswith("test-"):
            # Log the shape only: replies can carry the customer's name, phone and address
            logger.info(
                "Mock Send API dispatch (no live page token): keys=%s",
                sorted(payload.get("message") or {}) or payload.get("sender_action"),
            )
            return {"recipient_id": payload.get("recipient", {}).get("id"), "message_id": "mock_mid_123"}

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.page_access_token}",
        }

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                resp = await client.post(GRAPH_API_URL, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "Meta Send API HTTP error: status=%d, body=%s",
                    e.response.status_code,
                    e.response.text,
                )
                raise
            except Exception as e:
                logger.error("Meta Send API network/timeout error: %s", e)
                raise

    async def send_text_message(self, recipient_psid: str, text: str) -> dict[str, Any]:
        """Send a plain text message to a customer."""
        payload = {
            "recipient": {"id": recipient_psid},
            "messaging_type": "RESPONSE",
            "message": {"text": text},
        }
        return await self._post_payload(payload)

    async def send_reply(self, recipient_psid: str, text: str) -> dict[str, Any]:
        """Send a reply the way a person would: show typing, pause, then send."""
        if self.typing_delay_enabled:
            try:
                await self.send_typing_indicator(recipient_psid, "typing_on")
            except Exception as e:
                logger.warning("Failed to send typing indicator: %s", e)
            await asyncio.sleep(human_typing_delay(text))
        return await self.send_text_message(recipient_psid, text)

    async def send_typing_indicator(
        self, recipient_psid: str, action: str = "typing_on"
    ) -> dict[str, Any]:
        """
        Send typing_on, typing_off, or mark_seen sender actions.
        """
        payload = {
            "recipient": {"id": recipient_psid},
            "sender_action": action,
        }
        return await self._post_payload(payload, timeout=2.0)
