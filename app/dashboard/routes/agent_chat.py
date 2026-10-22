"""
Dashboard route and API for chatting with the AI sales agent.

Allows store owners/administrators to interact with the AI sales agent
simulating any customer with a clean slate (no preferences, past orders, or bias).
Includes live slots extraction inspection, state machine monitor, and session reset.
"""

import base64
import binascii
import logging
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from supabase import Client

from app.ai.gemini_provider import GeminiProvider
from app.ai.provider_interface import ImageInput
from app.config import Settings
from app.dashboard.middleware import require_auth
from app.dashboard.rate_limit import demo_chat_limiter
from app.db.repositories.conversations import ConversationRepository
from app.db.repositories.customers import CustomerRepository
from app.db.repositories.faqs import FAQRepository
from app.db.repositories.orders import OrderRepository
from app.db.repositories.products import ProductRepository
from app.db.repositories.settings import StoreSettingRepository
from app.dependencies import get_config, get_db
from app.models.conversation import ConversationState
from app.services.conversation_service import ConversationService
from app.services.images import MAX_IMAGE_BYTES, SUPPORTED_MIME_TYPES
from app.services.order_service import OrderService
from app.telegram.reporter import TelegramReporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard/chat", tags=["dashboard_agent_chat"])


class ChatMessagePayload(BaseModel):
    message: str = Field("", max_length=2000, description="Customer message text")
    image_data_url: str | None = Field(
        None, max_length=8_000_000, description="Optional photo as a data: URL (data:image/jpeg;base64,...)"
    )
    customer_name: str | None = Field(None, max_length=100, description="Optional customer name hint")
    session_id: str | None = Field(None, description="Simulated customer session PSID")


class ChatResetPayload(BaseModel):
    session_id: str | None = Field(None, description="Current simulated session PSID to reset")
    clear_history: bool = Field(True, description="Whether to start a completely new session")


class HandoffTogglePayload(BaseModel):
    session_id: str | None = Field(None, description="Simulated session PSID")
    is_handoff: bool = Field(False, description="Target human handoff status")


def _get_or_create_sim_session(user_id: str, requested_session: str | None = None) -> str:
    """Generate or sanitize a clean simulated customer PSID."""
    if requested_session and requested_session.startswith("sim_"):
        return requested_session
    # Generate clean simulated PSID for this user
    return f"sim_admin_{user_id}_{uuid.uuid4().hex[:8]}"


def _decode_image_data_url(data_url: str) -> ImageInput | None:
    """Turn a browser data: URL into an image for the model; None if not a supported image."""
    header, _, encoded = data_url.partition(",")
    mime_type = header.removeprefix("data:").removesuffix(";base64").lower()
    if not header.endswith(";base64") or mime_type not in SUPPORTED_MIME_TYPES:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    return ImageInput(data=data, mime_type=mime_type)


def _build_conversation_service(
    db: Client, config: Settings, store_id: str, send_alerts: bool = True
) -> tuple[ConversationService, ConversationRepository, CustomerRepository, StoreSettingRepository, ProductRepository]:
    """Assemble all repositories and the conversation orchestrator service.

    send_alerts=False keeps demo visitors from pinging the owner's Telegram.
    """
    conv_repo = ConversationRepository(db)
    customer_repo = CustomerRepository(db)
    product_repo = ProductRepository(db)
    faq_repo = FAQRepository(db)
    setting_repo = StoreSettingRepository(db)
    order_repo = OrderRepository(db)

    order_service = OrderService(
        order_repo=order_repo,
        product_repo=product_repo,
        setting_repo=setting_repo,
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
    )

    ai_provider = GeminiProvider(
        api_key=config.gemini_api_key,
        model_name=config.gemini_model,
    )

    conv_service = ConversationService(
        conversation_repo=conv_repo,
        customer_repo=customer_repo,
        product_repo=product_repo,
        faq_repo=faq_repo,
        setting_repo=setting_repo,
        order_service=order_service,
        ai_provider=ai_provider,
        alert_notifier=TelegramReporter(config.telegram_bot_token, config.telegram_chat_id) if send_alerts else None,
    )

    return conv_service, conv_repo, customer_repo, setting_repo, product_repo


@router.get("", response_class=HTMLResponse)
def show_agent_chat_studio(
    request: Request,
    session_id: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """
    Render the interactive Talk with Agent section in the admin dashboard.
    Simulates talking as any regular customer without pre-existing preferences.
    """
    store_id = user.get("store_id") or config.default_store_id
    user_id = str(user.get("id") or "admin")

    cookie_session = request.cookies.get("admin_sim_psid")
    effective_session_id = session_id or cookie_session or _get_or_create_sim_session(user_id)

    _, conv_repo, customer_repo, setting_repo, product_repo = _build_conversation_service(
        db, config, store_id
    )

    # 1. Customer profile (no preferences by default)
    customer = customer_repo.get_or_create(store_id, effective_session_id)
    if not customer or not isinstance(customer, dict):
        customer = {"id": "sim-cust-0000", "messenger_psid": effective_session_id, "name": None}

    customer_id = customer.get("id")

    # 2. Conversation session
    conv = conv_repo.get_or_create(store_id, effective_session_id, customer_id=customer_id)
    if not conv or not isinstance(conv, dict) or "id" not in conv:
        conv = {
            "id": "sim-conv-0000",
            "store_id": store_id,
            "messenger_psid": effective_session_id,
            "state": ConversationState.DISCOVERY.value,
            "collected_slots": {},
            "is_human_handoff": False,
            "created_at": "2026-10-18T00:00:00Z",
            "last_message_at": "2026-10-18T00:00:00Z",
        }

    conv_id = conv.get("id", "sim-conv-0000")
    messages = conv_repo.get_messages(conv_id, limit=50) if conv_id != "sim-conv-0000" else []

    # Store settings & catalog preview
    try:
        bot_config = setting_repo.get_bot_config(store_id) or {}
    except Exception:
        bot_config = {}

    try:
        active_products = product_repo.get_active_catalog(store_id) or []
    except Exception:
        active_products = []

    templates = request.app.state.templates
    response = templates.TemplateResponse(
        "dashboard/agent_chat.html",
        {
            "request": request,
            "user": user,
            "session_id": effective_session_id,
            "conversation": conv,
            "messages": messages,
            "bot_config": bot_config,
            "products_count": len(active_products),
            "active_page": "agent_chat",
        },
    )

    # Persist session in cookie for convenience
    response.set_cookie(
        key="admin_sim_psid",
        value=effective_session_id,
        max_age=86400 * 7,
        httponly=False,
        samesite="lax",
    )
    return response


@router.post("/send")
async def send_customer_message(
    payload: ChatMessagePayload,
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """
    Process incoming customer message from admin playground turn-by-turn.
    Returns agent replies, updated state, extracted slots, and AI metadata.
    """
    store_id = user.get("store_id") or config.default_store_id
    user_id = str(user.get("id") or "admin")
    # Only simulator sessions: a real customer's PSID must never be reachable from here
    psid = _get_or_create_sim_session(user_id, payload.session_id)

    if user.get("is_demo"):
        if demo_chat_limiter.is_limited(user_id):
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"success": False, "error": "وصلت للحد المسموح للحساب التجريبي، جرب بعد شوي."},
            )
        demo_chat_limiter.hit(user_id)

    images: list[ImageInput] = []
    if payload.image_data_url:
        image = _decode_image_data_url(payload.image_data_url)
        if not image:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "error": "الصورة غير مدعومة (JPG أو PNG أو WEBP بحد أقصى 5 ميغابايت)."},
            )
        images.append(image)
    if not payload.message.strip() and not images:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "error": "اكتب رسالة أو أرفق صورة."},
        )

    conv_service, conv_repo, customer_repo, _, _ = _build_conversation_service(
        db, config, store_id, send_alerts=not user.get("is_demo")
    )

    # Dispatch to conversation service orchestrator
    try:
        replies = await conv_service.handle_customer_message(
            store_id=store_id,
            messenger_psid=psid,
            user_text=payload.message.strip(),
            customer_name_hint=payload.customer_name.strip() if payload.customer_name else None,
            images=images,
        )
    except Exception as e:
        logger.error("Error generating agent response in playground: %s", e, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"حدث خطأ أثناء معالجة رسالة الوكيل: {str(e)}",
            },
        )

    # Fetch updated conversation session & metadata
    customer = customer_repo.get_or_create(store_id, psid)
    conv = conv_repo.get_or_create(store_id, psid, customer_id=customer.get("id"))
    conv_id = conv.get("id")

    recent_messages = conv_repo.get_recent_messages(conv_id, limit=2) if conv_id else []
    latest_ai_metadata = None
    for m in reversed(recent_messages):
        if m.get("direction") == "outbound" and m.get("ai_metadata"):
            latest_ai_metadata = m.get("ai_metadata")
            break

    return {
        "success": True,
        "replies": replies,
        # Only an empty reply needs explaining; skip the lookup otherwise
        "bot_enabled": bool(replies) or StoreSettingRepository(db).get_bot_config(store_id).get("bot_enabled", True),
        "conversation": {
            "id": conv_id,
            "state": conv.get("state", ConversationState.DISCOVERY.value),
            "collected_slots": conv.get("collected_slots") or {},
            "is_human_handoff": bool(conv.get("is_human_handoff")),
            "handoff_reason": conv.get("handoff_reason"),
        },
        "ai_metadata": latest_ai_metadata,
        "session_id": psid,
    }


@router.post("/reset")
def reset_chat_session(
    payload: ChatResetPayload = ChatResetPayload(),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """
    Reset conversation back to fresh customer with NO preferences or prior slots.
    Generates a new clean session PSID.
    """
    store_id = user.get("store_id") or config.default_store_id
    user_id = str(user.get("id") or "admin")

    new_psid = _get_or_create_sim_session(user_id)
    _, conv_repo, customer_repo, _, _ = _build_conversation_service(db, config, store_id)

    # If old session provided and caller asked to reset existing in-place:
    if payload.session_id and not payload.clear_history:
        old_psid = payload.session_id
        customer = customer_repo.get_or_create(store_id, old_psid)
        conv = conv_repo.get_or_create(store_id, old_psid, customer_id=customer.get("id"))
        if conv and conv.get("id"):
            conv_repo.update_state(
                store_id,
                conv["id"],
                state=ConversationState.DISCOVERY.value,
                collected_slots={},
            )
            conv_repo.set_human_handoff(store_id, conv["id"], is_handoff=False)
        effective_psid = old_psid
    else:
        # Create brand-new clean customer and conversation
        customer = customer_repo.get_or_create(store_id, new_psid)
        conv = conv_repo.get_or_create(store_id, new_psid, customer_id=customer.get("id"))
        effective_psid = new_psid

    resp = JSONResponse(
        content={
            "success": True,
            "message": "تم تصفير المحادثة والبدء كعميل جديد تماماً بدون أي تفضيلات مسبقة.",
            "session_id": effective_psid,
            "state": ConversationState.DISCOVERY.value,
            "collected_slots": {},
            "is_human_handoff": False,
        }
    )
    resp.set_cookie(
        key="admin_sim_psid",
        value=effective_psid,
        max_age=86400 * 7,
        httponly=False,
        samesite="lax",
    )
    return resp


@router.post("/handoff-toggle")
def toggle_agent_handoff(
    payload: HandoffTogglePayload,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Toggle human handoff status on the simulated testing conversation."""
    store_id = user.get("store_id") or config.default_store_id
    psid = _get_or_create_sim_session(str(user.get("id") or "admin"), payload.session_id)

    _, conv_repo, customer_repo, _, _ = _build_conversation_service(db, config, store_id)
    customer = customer_repo.get_or_create(store_id, psid)
    conv = conv_repo.get_or_create(store_id, psid, customer_id=customer.get("id"))

    if conv and conv.get("id"):
        conv_repo.set_human_handoff(
            store_id,
            conv["id"],
            is_handoff=payload.is_handoff,
            reason="Playground manual toggle",
        )
        updated_conv = conv_repo.get_by_id(store_id, conv["id"]) or {}
        return {
            "success": True,
            "is_human_handoff": bool(updated_conv.get("is_human_handoff")),
            "state": updated_conv.get("state", ConversationState.DISCOVERY.value),
        }

    return {"success": False, "error": "المحادثة غير موجودة"}
