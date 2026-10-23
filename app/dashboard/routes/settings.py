"""
Dashboard store settings and bot configuration routes.
"""

from typing import Any
from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.settings import DEFAULT_DELIVERY_FEE_JOD, StoreSettingRepository
from app.dependencies import get_config, get_db
from app.services.branding import OPTIONAL_DEFAULTS, REQUIRED_DEFAULTS, invalidate_branding

router = APIRouter(prefix="/dashboard/settings", tags=["dashboard_settings"])


def mask_secret(value: str) -> str:
    """Mask secret token, displaying only the last 4 characters."""
    if not value or len(value) <= 4:
        return "••••••••"
    return "••••••••" + value[-4:]


@router.get("", response_class=HTMLResponse)
def show_settings(
    request: Request,
    msg: str | None = Query(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """View store and bot personality settings."""
    store_id = user.get("store_id") or config.default_store_id
    setting_repo = StoreSettingRepository(db)
    settings_dict = setting_repo.get_all(store_id)

    # Masked API keys from env config
    masked_keys = {
        "gemini_api_key": mask_secret(config.gemini_api_key),
        "meta_page_access_token": mask_secret(config.meta_page_access_token),
        "meta_app_secret": mask_secret(config.meta_app_secret),
        "telegram_bot_token": mask_secret(config.telegram_bot_token),
        "telegram_chat_id": config.telegram_chat_id or "—",
    }

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/settings/index.html",
        {
            "request": request,
            "user": user,
            "settings": settings_dict,
            "masked_keys": masked_keys,
            "branding_defaults": {**REQUIRED_DEFAULTS, **OPTIONAL_DEFAULTS},
            "default_delivery_fee": f"{DEFAULT_DELIVERY_FEE_JOD:.3f}",
            "msg": msg,
            "active_page": "settings",
        },
    )


@router.post("")
def update_settings(
    store_name: str = Form("متجر التقوى"),
    bot_greeting: str = Form(...),
    bot_tone: str = Form(...),
    store_description: str = Form(""),
    working_hours: str = Form(""),
    return_policy: str = Form(""),
    human_handoff_message: str = Form(...),
    delivery_fee_jod: float = Form(DEFAULT_DELIVERY_FEE_JOD),
    bot_enabled: bool = Form(False),
    store_tagline: str | None = Form(None),
    sf_header_badge: str | None = Form(None),
    sf_header_seal: str | None = Form(None),
    sf_hero_pill: str | None = Form(None),
    sf_hero_title_gold: str | None = Form(None),
    sf_hero_title_white: str | None = Form(None),
    sf_hero_subtitle: str | None = Form(None),
    sf_trust_badges: str | None = Form(None),
    sf_cta_label: str | None = Form(None),
    sf_footer_about: str | None = Form(None),
    sf_location: str | None = Form(None),
    privacy_contact: str | None = Form(None),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Save store settings and bot personality."""
    store_id = user.get("store_id") or config.default_store_id
    setting_repo = StoreSettingRepository(db)

    # Whitespace-only input passes the browser's `required`; keep the previous value instead
    current = setting_repo.get_all(store_id)
    required_text = {
        "store_name": (store_name, "text"),
        "bot_greeting": (bot_greeting, "textarea"),
        "bot_tone": (bot_tone, "textarea"),
        "human_handoff_message": (human_handoff_message, "textarea"),
    }
    for key, (value, setting_type) in required_text.items():
        value = value.strip() or current.get(key, "") or REQUIRED_DEFAULTS.get(key, "")
        if value:
            setting_repo.set_value(store_id, key, value, setting_type)

    setting_repo.set_value(store_id, "store_description", store_description.strip(), "textarea")
    setting_repo.set_value(store_id, "working_hours", working_hours.strip())
    setting_repo.set_value(store_id, "return_policy", return_policy.strip(), "textarea")
    setting_repo.set_value(store_id, "delivery_fee_jod", f"{max(delivery_fee_jod, 0):.3f}", "number")
    setting_repo.set_value(store_id, "bot_enabled", "true" if bot_enabled else "false", "boolean")

    # Storefront identity & copy (only fields present in the submitted form)
    storefront_fields = {
        "store_tagline": store_tagline,
        "sf_header_badge": sf_header_badge,
        "sf_header_seal": sf_header_seal,
        "sf_hero_pill": sf_hero_pill,
        "sf_hero_title_gold": sf_hero_title_gold,
        "sf_hero_title_white": sf_hero_title_white,
        "sf_hero_subtitle": sf_hero_subtitle,
        "sf_trust_badges": sf_trust_badges,
        "sf_cta_label": sf_cta_label,
        "sf_footer_about": sf_footer_about,
        "sf_location": sf_location,
        "privacy_contact": privacy_contact,
    }
    multiline = {"sf_hero_subtitle", "sf_trust_badges", "sf_footer_about"}
    for key, value in storefront_fields.items():
        if value is not None:
            setting_repo.set_value(store_id, key, value.strip(), "textarea" if key in multiline else "text")
    invalidate_branding(store_id)

    return RedirectResponse(
        url="/dashboard/settings?msg=saved",
        status_code=status.HTTP_303_SEE_OTHER,
    )
