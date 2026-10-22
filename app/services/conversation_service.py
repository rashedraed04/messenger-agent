"""
Conversation service orchestrator.

Coordinates AI provider, order state machine, database persistence,
and customer interaction flow.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from app.ai.prompt_builder import build_system_prompt
from app.db.repositories.product_types import load_types_by_name
from app.ai.provider_interface import AIProvider, ImageInput
from app.db.repositories.conversations import ConversationRepository
from app.db.repositories.customers import CustomerRepository
from app.db.repositories.faqs import FAQRepository
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.models.conversation import ConversationState, MessageDirection
from app.services.order_service import OrderService
from app.services.images import fetch_catalog_image
from app.services.product_service import normalize_arabic_text
from app.services.text_humanizer import humanize_reply
from app.telegram.reporter import TelegramReporter, format_angry_customer_alert

logger = logging.getLogger(__name__)

# Photo turns: how a photo is stored in history, and how many catalog photos the model sees
PHOTO_MARKER = "📷 [صورة]"
PHOTO_ONLY_PROMPT = "(الزبون بعث صورة بدون كلام)"
CUSTOMER_PHOTO_LABEL = "الصورة اللي بعثها الزبون:"
MAX_CATALOG_REFERENCE_IMAGES = 20
UNREADABLE_PHOTO_REPLY = (
    "وصلتني الصورة بس مش قادر أفتحها منيح عندي 🙏 "
    "شو اسم المنتج أو شو بتدور عليه بالزبط؟"
)

# Rolling conversation memory passed to the model
MEMORY_WINDOW = timedelta(hours=12)
MEMORY_MAX_MESSAGES = 20

FRESH_GREETING_REPLY = (
    "هلا والله، نورت 🌸 كيف بقدر أساعدك؟ "
    "بتدور على هدية لحاج أو معتمر ولا ببالك شي معين؟"
)

CANCEL_REPLY = "ولا يهمك يا غالي، لغيتلك الطلب. وإذا لزمك أي شي بوقت ثاني احنا موجودين."
HANDOFF_REPLY = "تكرم عينك، هسا بخلي حدا من الشباب يحكي معك بأقرب وقت 🙏"
BOT_DISABLED_REPLY = "هلا والله، ثواني وبرد عليك حدا من الشباب."
FINALIZE_ERROR_REPLY = (
    "معلش صار عندي لخبطة بسيطة وأنا بثبت الطلب، "
    "هسا حدا من الشباب رح يتابع معك ويأكدلك إياه."
)

# Normalized greeting words; a message made only of these is a pure greeting
GREETING_TOKENS = {
    "مرحبا", "مرحبتين", "مرحبه", "هلا", "اهلا", "هاي", "هلو", "السلام", "سلام", "عليكم",
    "مساء", "صباح", "الخير", "النور", "يا", "والله", "hi", "hello", "hey", "salam",
}


def is_pure_greeting(text: str) -> bool:
    """True for messages like "مرحبا", "السلام عليكم", "مساء الخير", "هلا والله"."""
    tokens = re.findall(r"\w+", normalize_arabic_text(text))
    return bool(tokens) and all(tok in GREETING_TOKENS for tok in tokens)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse a Supabase timestamp (ISO string or datetime) into an aware UTC datetime."""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ConversationService:
    """End-to-end conversation turn processing."""

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        customer_repo: CustomerRepository,
        product_repo: ProductRepository,
        faq_repo: FAQRepository,
        setting_repo: StoreSettingRepository,
        order_service: OrderService,
        ai_provider: AIProvider,
        alert_notifier: TelegramReporter | None = None,
        catalog_image_fetcher: Callable[[str], Awaitable[ImageInput | None]] = fetch_catalog_image,
    ):
        self.conversation_repo = conversation_repo
        self.customer_repo = customer_repo
        self.product_repo = product_repo
        self.faq_repo = faq_repo
        self.setting_repo = setting_repo
        self.order_service = order_service
        self.ai_provider = ai_provider
        self.alert_notifier = alert_notifier
        self.catalog_image_fetcher = catalog_image_fetcher

    async def handle_customer_message(
        self,
        store_id: str,
        messenger_psid: str,
        user_text: str,
        customer_name_hint: str | None = None,
        images: list[ImageInput] | None = None,
        unreadable_images: int = 0,
    ) -> list[str]:
        """
        Process a customer message end-to-end and return list of reply texts.

        Args:
            store_id: Store ID.
            messenger_psid: Customer Page-Scoped ID.
            user_text: Raw incoming message text (may be empty for a photo).
            customer_name_hint: Optional profile name from Messenger.
            images: Photos the customer sent with this message.
            unreadable_images: Photos that were sent but could not be downloaded.

        Returns:
            List of response message strings to send via Meta Send API.
        """
        images = images or []
        has_photo = bool(images) or unreadable_images > 0
        # 1. Customer profile
        customer = self.customer_repo.get_or_create(
            store_id, messenger_psid, name=customer_name_hint
        )
        customer_id = customer.get("id")

        # 2. Conversation session
        conversation = self.conversation_repo.get_or_create(
            store_id, messenger_psid, customer_id=customer_id
        )
        conversation_id = conversation["id"]
        current_state = ConversationState(conversation.get("state", ConversationState.DISCOVERY.value))
        collected_slots = conversation.get("collected_slots") or {}

        # 2b. Session freshness: anything older than the memory window is abandoned,
        # and a finished order (confirmed/cancelled) means the next message starts fresh.
        now = datetime.now(timezone.utc)
        window_start = now - MEMORY_WINDOW
        last_activity = _parse_timestamp(conversation.get("last_message_at"))
        is_stale = last_activity is not None and last_activity < window_start

        if is_stale:
            # Handed-off chats come back to the bot too: there is no dashboard toggle,
            # the owner answers from the Facebook Page inbox in the meantime.
            if conversation.get("is_human_handoff"):
                logger.info("Conversation %s quiet since %s; bot resumes after handoff.", conversation_id, last_activity.isoformat())
                self.conversation_repo.set_human_handoff(
                    store_id, conversation_id, is_handoff=False, reason="Resumed after 12 quiet hours"
                )
                conversation["is_human_handoff"] = False
            if collected_slots and current_state != ConversationState.CONFIRMED:
                logger.info(
                    "Conversation %s idle since %s; discarding stale unconfirmed slots: %s",
                    conversation_id, last_activity.isoformat(), collected_slots,
                )
            current_state = ConversationState.DISCOVERY
            collected_slots = {}
            self.conversation_repo.update_state(
                store_id, conversation_id, state=current_state, collected_slots={}
            )
        elif current_state in (ConversationState.CONFIRMED, ConversationState.CANCELLED):
            current_state = ConversationState.DISCOVERY
            collected_slots = {}

        # 2c. Rolling memory: the latest messages from the last 12 hours, loaded BEFORE
        # storing the new inbound message so the current turn isn't duplicated.
        past_messages = self.conversation_repo.get_recent_messages(
            conversation_id, since=window_start, limit=MEMORY_MAX_MESSAGES
        )
        formatted_history = [
            {
                "role": "user" if m.get("direction") == MessageDirection.INBOUND.value else "model",
                "content": m.get("content", ""),
            }
            for m in past_messages
            if m.get("content")
        ]

        # 3. Store inbound message (a photo is stored as a marker plus its URL)
        image_urls = [img.source_url for img in images if img.source_url]
        self.conversation_repo.add_message(
            conversation_id=conversation_id,
            direction=MessageDirection.INBOUND.value,
            content=f"{PHOTO_MARKER}\n{user_text}".strip() if has_photo else user_text,
            message_type="image" if has_photo else "text",
            ai_metadata={"image_urls": image_urls} if image_urls else None,
        )

        # 4. Check if human handoff is already active
        if conversation.get("is_human_handoff"):
            logger.info("Conversation %s is in human handoff mode; skipping AI response.", conversation_id)
            return []

        # 5. Check if bot is enabled for this store
        bot_config = self.setting_repo.get_bot_config(store_id)
        if not bot_config.get("bot_enabled", True):
            handoff_msg = bot_config.get("human_handoff_message", BOT_DISABLED_REPLY)
            return [humanize_reply(handoff_msg)]

        # 5b. A photo we couldn't download and no text: nothing for the model to work with
        if unreadable_images and not images and not user_text.strip():
            reply = humanize_reply(UNREADABLE_PHOTO_REPLY)
            self.conversation_repo.add_message(
                conversation_id=conversation_id,
                direction=MessageDirection.OUTBOUND.value,
                content=reply,
            )
            return [reply]

        # 6. Load catalog and FAQs
        catalog = self.product_repo.get_active_catalog(store_id)
        product_types = load_types_by_name(getattr(self.product_repo, "client", None), store_id)
        faqs = self.faq_repo.list_active(store_id)

        # 6b. Photo turn: catalog photos first (labelled with the product name), then the customer's
        ai_images: list[ImageInput] = []
        if images:
            ai_images = await self._catalog_reference_images(catalog)
            ai_images += [img.model_copy(update={"label": CUSTOMER_PHOTO_LABEL}) for img in images]

        # 7-8. Build system prompt (history was loaded in step 2c)
        has_recent_context = bool(formatted_history) or bool(collected_slots)
        system_prompt = build_system_prompt(
            bot_config=bot_config,
            catalog=catalog,
            faqs=faqs,
            current_state=current_state.value,
            collected_slots=collected_slots,
            has_recent_context=has_recent_context,
            product_types=product_types,
        )

        # 9. Call AI Provider
        ai_resp = await self.ai_provider.generate_response(
            system_instruction=system_prompt,
            user_message=user_text or (PHOTO_ONLY_PROMPT if images else ""),
            conversation_history=formatted_history,
            timeout_seconds=25.0,
            images=ai_images or None,
        )

        # 10. Process state machine transition
        next_state, updated_slots, action_note = self.order_service.process_state_transition(
            store_id=store_id,
            current_state=current_state,
            collected_slots=collected_slots,
            user_message=user_text,
            extracted_slots=ai_resp.extracted_slots,
            intent=ai_resp.intent,
        )

        responses_to_send: list[str] = []

        # 11. Branch by resulting state
        if next_state == ConversationState.HUMAN_HANDOFF:
            self.conversation_repo.set_human_handoff(
                store_id, conversation_id, is_handoff=True, reason=action_note
            )
            handoff_msg = bot_config.get("human_handoff_message", HANDOFF_REPLY)
            responses_to_send.append(handoff_msg)

        elif next_state == ConversationState.CANCELLED:
            self.conversation_repo.update_state(
                store_id, conversation_id, state=ConversationState.CANCELLED, collected_slots={}
            )
            responses_to_send.append(CANCEL_REPLY)

        elif next_state == ConversationState.CONFIRMED:
            try:
                final_order = self.order_service.finalize_order(
                    store_id=store_id,
                    conversation_id=conversation_id,
                    customer_id=customer_id,
                    collected_slots=updated_slots,
                )
                order_num = final_order.get("order_number")
                confirm_msg = (
                    f"تمام التمام، اعتمدتلك الطلب ورقمه {order_num} 🌹\n"
                    f"رح نسلّمه لشركة التوصيل، وهمه بتواصلوا معك قبل ما يوصلك.\n"
                    f"تسلم على ثقتك بـ {bot_config.get('store_name', 'محلنا')}، ونورتنا."
                )
                responses_to_send.append(confirm_msg)
                # Reset conversation state and slots after successful completion
                self.conversation_repo.update_state(
                    store_id,
                    conversation_id,
                    state=ConversationState.CONFIRMED,
                    collected_slots={},
                    current_order_id=final_order.get("id"),
                )
            except Exception as e:
                logger.error("Failed to finalize order: %s", e)
                responses_to_send.append(FINALIZE_ERROR_REPLY)
                self.conversation_repo.set_human_handoff(
                    store_id, conversation_id, is_handoff=True, reason=f"Order finalization error: {e}"
                )

        elif next_state == ConversationState.AWAITING_CONFIRMATION:
            # Deterministic price calculation and Arabic summary
            price_summary = self.order_service.calculate_price_summary(store_id, updated_slots)
            if price_summary:
                summary_msg = price_summary.format_arabic_summary(
                    customer_name=updated_slots.get("customer_name"),
                    customer_phone=updated_slots.get("customer_phone"),
                    address_detail=updated_slots.get("address_detail"),
                )
                responses_to_send.append(summary_msg)
            else:
                responses_to_send.append(ai_resp.response_text or "أعتمدلك الطلب؟")

            self.conversation_repo.update_state(
                store_id, conversation_id, state=next_state, collected_slots=updated_slots
            )

        else:
            # DISCOVERY, PRODUCT_SELECTION, or COLLECTING_DETAILS
            reply_text = ai_resp.response_text or "هلا والله، كيف بقدر أساعدك؟"
            # A photo with "مرحبا" asks about that product, so naming it isn't a pitch
            if is_pure_greeting(user_text) and not images:
                reply_text = self._guard_greeting_reply(
                    reply_text, catalog, collected_slots, has_recent_context
                )
            responses_to_send.append(reply_text)

            self.conversation_repo.update_state(
                store_id, conversation_id, state=next_state, collected_slots=updated_slots
            )

        # 12. Humanize, then save outbound messages to database (stored text == sent text)
        responses_to_send = [humanize_reply(msg) for msg in responses_to_send]
        ai_meta = {
            "model_name": ai_resp.model_name,
            "latency_ms": ai_resp.latency_ms,
            "intent": ai_resp.intent,
            "suggested_state": ai_resp.suggested_state,
            "customer_mood": "angry" if ai_resp.customer_angry else "normal",
        }

        # 13. Angry customer: alert the owner on Telegram, at most once per memory window
        if ai_resp.customer_angry and not self._angry_alert_already_sent(past_messages):
            ai_meta["angry_alert"] = await self._send_angry_alert(
                store_id=store_id,
                messenger_psid=messenger_psid,
                conversation_id=conversation_id,
                customer_name=customer.get("name") or customer_name_hint or collected_slots.get("customer_name"),
                message_text=user_text or PHOTO_MARKER,
                store_name=bot_config.get("store_name", ""),
            )

        for out_msg in responses_to_send:
            self.conversation_repo.add_message(
                conversation_id=conversation_id,
                direction=MessageDirection.OUTBOUND.value,
                content=out_msg,
                ai_metadata=ai_meta,
            )

        return responses_to_send

    async def _catalog_reference_images(self, catalog: list[dict[str, Any]]) -> list[ImageInput]:
        """Catalog products' photos, each labelled with its name, for matching a customer photo."""
        products = [p for p in catalog if (p.get("image_url") or "").startswith(("http://", "https://"))]
        products = products[:MAX_CATALOG_REFERENCE_IMAGES]
        fetched = await asyncio.gather(
            *(self.catalog_image_fetcher(p["image_url"]) for p in products),
            return_exceptions=True,
        )
        return [
            img.model_copy(update={"label": f"صورة من الكتالوج: {p['name_ar']}"})
            for p, img in zip(products, fetched)
            if isinstance(img, ImageInput)
        ]

    @staticmethod
    def _angry_alert_already_sent(past_messages: list[dict[str, Any]]) -> bool:
        return any((m.get("ai_metadata") or {}).get("angry_alert") for m in past_messages)

    async def _send_angry_alert(
        self,
        store_id: str,
        messenger_psid: str,
        conversation_id: str,
        customer_name: str | None,
        message_text: str,
        store_name: str,
    ) -> bool:
        """Send the Telegram alert; never lets a Telegram failure break the reply."""
        if not self.alert_notifier:
            return False
        text = format_angry_customer_alert(
            store_name=store_name,
            customer_name=customer_name,
            message_text=message_text,
            is_test=messenger_psid.startswith("sim_"),
        )
        try:
            sent = await self.alert_notifier.send_message(text)
        except Exception as e:
            logger.error("Angry customer alert failed for store %s: %s", store_id, e)
            return False
        if sent:
            logger.info("Angry customer alert sent for conversation %s", conversation_id)
        return sent

    @staticmethod
    def _guard_greeting_reply(
        reply_text: str,
        catalog: list[dict[str, Any]],
        collected_slots: dict[str, Any],
        has_recent_context: bool,
    ) -> str:
        """
        A bare greeting must never be answered with an unprompted product pitch.

        Fresh customer: any product name in the reply is a hallucination -> standard welcome.
        Returning customer: only products already in their cart may be referenced.
        """
        cart_names = {
            normalize_arabic_text(p.get("product_name") or "")
            for p in collected_slots.get("products") or []
        }
        normalized_reply = normalize_arabic_text(reply_text)
        for prod in catalog:
            name_ar = normalize_arabic_text(prod.get("name_ar") or "")
            if name_ar in cart_names:
                continue
            first_word = name_ar.split()[0] if name_ar else ""
            name_en = (prod.get("name_en") or "").lower()
            if (len(first_word) >= 3 and first_word in normalized_reply) or (
                name_en and name_en in normalized_reply
            ):
                logger.warning("Greeting reply mentioned unrequested product %r; replacing.", prod.get("name_ar"))
                break
        else:
            return reply_text

        if has_recent_context and collected_slots.get("products"):
            names = "، ".join(p.get("product_name", "") for p in collected_slots["products"])
            return (
                f"هلا والله من جديد 🌸 كنا نحكي عن طلبك لـ {names}، "
                "بتحب نكمل ونثبتلك الطلب ولا حابب تعدل عليه؟"
            )
        return FRESH_GREETING_REPLY
