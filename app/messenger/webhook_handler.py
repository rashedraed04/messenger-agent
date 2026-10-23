"""
Meta Messenger webhook signature verification and event dispatcher.
"""

import asyncio
import hashlib
import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from app.ai.provider_interface import ImageInput
from app.dashboard.rate_limit import webhook_sender_limiter
from app.db.repositories.webhook_events import WebhookEventRepository
from app.messenger.message_types import IncomingMessage, WebhookPayload
from app.messenger.send_api import MessengerSendAPI
from app.services.conversation_service import ConversationService
from app.services.images import fetch_messenger_image

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_MESSAGE = 3
# Longer customer messages are cut before reaching the AI
MAX_TEXT_CHARS = 2000


def extract_image_urls(message: IncomingMessage) -> list[str]:
    """URLs of photos attached to a message (stickers, also sent as images, are skipped)."""
    urls = []
    for att in message.attachments or []:
        payload = att.get("payload") or {}
        if att.get("type") == "image" and payload.get("url") and not payload.get("sticker_id"):
            urls.append(payload["url"])
    return urls[:MAX_IMAGES_PER_MESSAGE]


def verify_hub_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """
    Verify X-Hub-Signature-256 header using HMAC-SHA256.

    Args:
        payload_bytes: Raw HTTP request body.
        signature_header: Value of X-Hub-Signature-256 header (sha256=...).
        app_secret: Meta App Secret.

    Returns:
        True if valid or in development bypass mode, False otherwise.
    """
    if not app_secret or app_secret.startswith("test-"):
        # Development / test mode bypass
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("Missing or malformed X-Hub-Signature-256 header")
        return False

    expected_sig = signature_header[7:]  # strip 'sha256='
    calculated_sig = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, calculated_sig)


class WebhookHandler:
    """Processes incoming Messenger webhook events with idempotency and dispatch."""

    def __init__(
        self,
        event_repo: WebhookEventRepository,
        conversation_service: ConversationService,
        send_api: MessengerSendAPI,
        image_fetcher: Callable[[str], Awaitable[ImageInput | None]] = fetch_messenger_image,
    ):
        self.event_repo = event_repo
        self.conversation_service = conversation_service
        self.send_api = send_api
        self.image_fetcher = image_fetcher

    async def process_payload(
        self,
        store_id: str,
        payload_dict: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Parse and process an incoming Meta webhook payload.
        Deduplicates retried events using event_mid.
        """
        results = []
        if payload_dict.get("object") != "page":
            logger.info("Ignoring non-page webhook object: %s", payload_dict.get("object"))
            return results

        try:
            payload = WebhookPayload.model_validate(payload_dict)
        except Exception as e:
            logger.error("Failed to parse WebhookPayload: %s", e)
            return results

        for entry in payload.entry:
            for item in entry.messaging:
                sender_psid = item.sender.id

                # Extract text and mid from either regular message or postback
                mid = None
                user_text = ""
                image_urls: list[str] = []

                if item.message:
                    mid = item.message.mid
                    user_text = item.message.text or ""
                    image_urls = extract_image_urls(item.message)
                    # Handle quick replies
                    if item.message.quick_reply and item.message.quick_reply.payload:
                        user_text = item.message.quick_reply.payload

                elif item.postback:
                    mid = item.postback.mid or f"postback_{entry.id}_{item.timestamp}"
                    user_text = item.postback.payload or item.postback.title or ""

                if not mid or not (user_text or image_urls):
                    continue

                # Idempotency check: Ignore duplicate delivery from Meta
                is_new = self.event_repo.mark_processed_if_new(store_id, mid)
                if not is_new:
                    logger.info("Skipping duplicate webhook event with mid=%s", mid)
                    results.append({"mid": mid, "status": "duplicate_skipped"})
                    continue

                # Per-sender throttle: a spamming sender gets no AI call and no reply
                if webhook_sender_limiter.is_limited(sender_psid):
                    logger.warning("Rate-limited webhook sender psid=%s", sender_psid)
                    results.append({"mid": mid, "status": "rate_limited"})
                    continue
                webhook_sender_limiter.hit(sender_psid)

                user_text = user_text[:MAX_TEXT_CHARS]

                # Typing indicator only when the bot is switched on; a disabled bot shows nothing
                bot_enabled = self.conversation_service.is_bot_enabled(store_id)
                if bot_enabled:
                    try:
                        await self.send_api.send_typing_indicator(sender_psid, "typing_on")
                    except Exception as e:
                        logger.warning("Failed to send typing indicator: %s", e)

                # Process turn through conversation engine
                try:
                    images = await self._download_images(image_urls)
                    replies = await self.conversation_service.handle_customer_message(
                        store_id=store_id,
                        messenger_psid=sender_psid,
                        user_text=user_text,
                        images=images,
                        unreadable_images=len(image_urls) - len(images),
                    )

                    # Send all replies via Meta Send API
                    for reply_text in replies:
                        await self.send_api.send_reply(sender_psid, reply_text)
                    # No reply (e.g. chat handed to the owner): clear the dots we showed
                    if not replies and bot_enabled:
                        try:
                            await self.send_api.send_typing_indicator(sender_psid, "typing_off")
                        except Exception as e:
                            logger.warning("Failed to clear typing indicator: %s", e)

                    results.append({"mid": mid, "status": "processed", "replies_sent": len(replies)})
                except Exception as e:
                    logger.exception("Error processing message for psid=%s: %s", sender_psid, e)
                    # Attempt to send generic fallback apology
                    try:
                        fallback = "معلش صار خلل بسيط عندي، ابعث رسالتك كمان مرة لو سمحت 🙏"
                        await self.send_api.send_text_message(sender_psid, fallback)
                    except Exception:
                        pass
                    results.append({"mid": mid, "status": "error", "error": str(e)})

        return results

    async def _download_images(self, urls: list[str]) -> list[ImageInput]:
        """Download the customer's photos; ones that fail are dropped (and counted by the caller)."""
        if not urls:
            return []
        results = await asyncio.gather(*(self.image_fetcher(u) for u in urls), return_exceptions=True)
        return [img for img in results if isinstance(img, ImageInput)]
