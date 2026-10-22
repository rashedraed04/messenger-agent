"""
Store identity and storefront copy, editable from the dashboard settings page.

Every template receives the result as `brand` through a Jinja context
processor (see app.main), so the store name, tagline and public page texts
are never hard-coded in templates.
"""

import logging
import time
from typing import Any
from supabase import Client

from app.db.repositories.settings import StoreSettingRepository

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60

# Keys that always need a value; saving them empty falls back to the default
REQUIRED_DEFAULTS: dict[str, str] = {
    "store_name": "متجر التقوى",
    "sf_hero_title_gold": "هدايا الحج والعمرة",
    "sf_cta_label": "طلب عبر ماسنجر / استفسر عن السعر",
}

# Keys the admin may clear to hide that element
OPTIONAL_DEFAULTS: dict[str, str] = {
    "store_tagline": "لبضائع وهدايا الحج والعمرة",
    "sf_header_badge": "هدايا الحج والعمرة",
    "sf_header_seal": "جودة مضمونة",
    "sf_hero_pill": "",
    "sf_hero_title_white": "بين يديك",
    "sf_hero_subtitle": (
        "تصفح تشكيلة مختارة من بضائع وهدايا الحج والعمرة واستفسر عن السعر أو اطلبها "
        "فوراً عبر ماسنجر مع توصيل سريع لجميع المحافظات والدفع عند الاستلام."
    ),
    "sf_trust_badges": "\n".join([
        "منتجات أصلية بجودة مضمونة",
        "توصيل لكافة محافظات الأردن الـ 12",
        "الدفع نقداً عند الاستلام (كاش)",
        "طلب مباشر وسريع عبر ماسنجر",
    ]),
    "sf_footer_about": "وجهتك الأولى لهدايا الحجاج والمعتمرين ومستلزمات الحج والعمرة في المملكة الأردنية الهاشمية",
    "sf_location": "عمان، الأردن",
}

BRANDING_KEYS = (*REQUIRED_DEFAULTS, *OPTIONAL_DEFAULTS)

# Icons cycled across the trust badges (one badge per line in the setting)
TRUST_ICONS = ("bi-shield-fill-check", "bi-truck", "bi-cash-coin", "bi-chat-heart-fill", "bi-star-fill", "bi-gift-fill")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _initial(store_name: str) -> str:
    """Avatar letter: 'متجر التقوى' -> 'ت' (skips the word متجر and the article ال)."""
    word = store_name.replace("متجر", "").strip() or store_name
    if word.startswith("ال") and len(word) > 2:
        word = word[2:]
    return word[:1]


def build_branding(settings: dict[str, str]) -> dict[str, Any]:
    """Merge saved settings over the defaults into the `brand` template object."""
    values: dict[str, str] = {}
    for key, default in REQUIRED_DEFAULTS.items():
        values[key] = (settings.get(key) or "").strip() or default
    for key, default in OPTIONAL_DEFAULTS.items():
        values[key] = settings[key].strip() if key in settings and settings[key] is not None else default

    badges = [line.strip() for line in values["sf_trust_badges"].splitlines() if line.strip()]
    store_name = values["store_name"]
    tagline = values["store_tagline"]
    return {
        **values,
        "full_name": f"{store_name} {tagline}".strip(),
        "initial": _initial(store_name),
        "trust_badges": [
            {"text": text, "icon": TRUST_ICONS[i % len(TRUST_ICONS)]} for i, text in enumerate(badges)
        ],
    }


def get_branding(db: Client, store_id: str, ttl: float = CACHE_TTL_SECONDS) -> dict[str, Any]:
    """Branding for a store, cached for `ttl` seconds; defaults if settings can't be read."""
    now = time.monotonic()
    cached = _cache.get(store_id)
    if ttl > 0 and cached and now - cached[0] < ttl:
        return cached[1]

    try:
        settings = StoreSettingRepository(db).get_all(store_id)
        if not isinstance(settings, dict):
            settings = {}
    except Exception as e:
        logger.info("Branding fallback to defaults: %s", e)
        settings = {}

    branding = build_branding(settings)
    if ttl > 0:
        _cache[store_id] = (now, branding)
    return branding


def invalidate_branding(store_id: str | None = None) -> None:
    """Drop cached branding after the settings change."""
    if store_id is None:
        _cache.clear()
    else:
        _cache.pop(store_id, None)
