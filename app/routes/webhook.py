"""
Meta Messenger webhook endpoints.

GET  /webhook — Meta verification challenge
POST /webhook — Inbound events receiver (messages, postbacks)
"""

import json
import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from supabase import Client

from app.ai.gemini_provider import GeminiProvider
from app.config import Settings
from app.db.repositories.conversations import ConversationRepository
from app.db.repositories.customers import CustomerRepository
from app.db.repositories.faqs import FAQRepository
from app.db.repositories.orders import OrderRepository
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.db.repositories.webhook_events import WebhookEventRepository
from app.dependencies import get_config, get_db
from app.messenger.send_api import MessengerSendAPI
from app.messenger.webhook_handler import WebhookHandler, verify_hub_signature
from app.services.conversation_service import ConversationService
from app.services.order_service import OrderService
from app.telegram.reporter import TelegramReporter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["messenger_webhook"])


@router.get("/webhook", status_code=status.HTTP_200_OK)
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    settings: Settings = Depends(get_config),
):
    """
    Handle Meta's Webhook verification GET request.
    Echoes back hub.challenge if hub.verify_token matches META_VERIFY_TOKEN.
    """
    # An unset META_VERIFY_TOKEN must never match an empty hub.verify_token
    if (
        hub_mode == "subscribe"
        and settings.meta_verify_token
        and hub_verify_token == settings.meta_verify_token
    ):
        logger.info("Webhook verification challenge passed successfully.")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning("Webhook verification failed: mode or verify token mismatch")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Verification token mismatch",
    )


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_webhook_event(
    request: Request,
    x_hub_signature_256: str | None = Header(None, alias="x-hub-signature-256"),
    settings: Settings = Depends(get_config),
    db: Client = Depends(get_db),
):
    """
    Receive and process inbound Facebook Messenger webhook events.
    Synchronously handled within request lifecycle to satisfy Cloud Run CPU throttling constraints.
    """
    payload_bytes = await request.body()

    # 1. Verify HMAC-SHA256 signature
    is_valid = verify_hub_signature(
        payload_bytes=payload_bytes,
        signature_header=x_hub_signature_256,
        app_secret=settings.meta_app_secret,
    )
    if not is_valid:
        logger.warning("Rejected webhook: invalid X-Hub-Signature-256")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook signature",
        )

    # 2. Parse JSON
    try:
        payload_dict = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error("Failed to decode webhook JSON: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # 3. Assemble service dependencies
    store_id = settings.default_store_id

    event_repo = WebhookEventRepository(db)
    product_repo = ProductRepository(db)
    order_repo = OrderRepository(db)
    conv_repo = ConversationRepository(db)
    customer_repo = CustomerRepository(db)
    faq_repo = FAQRepository(db)
    setting_repo = StoreSettingRepository(db)

    order_service = OrderService(
        order_repo=order_repo,
        product_repo=product_repo,
        setting_repo=setting_repo,
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
    )

    ai_provider = GeminiProvider(
        api_key=settings.gemini_api_key,
        model_name=settings.gemini_model,
    )

    conv_service = ConversationService(
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
        product_repo=product_repo,
        faq_repo=faq_repo,
        setting_repo=setting_repo,
        order_service=order_service,
        ai_provider=ai_provider,
        alert_notifier=TelegramReporter(settings.telegram_bot_token, settings.telegram_chat_id),
    )

    send_api = MessengerSendAPI(
        page_access_token=settings.meta_page_access_token,
        typing_delay_enabled=settings.enable_typing_delay,
    )

    handler = WebhookHandler(
        event_repo=event_repo,
        conversation_service=conv_service,
        send_api=send_api,
    )

    # 4. Synchronous execution
    results = await handler.process_payload(store_id=store_id, payload_dict=payload_dict)

    return {"status": "ok", "results": results}
