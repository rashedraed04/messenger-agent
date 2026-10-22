"""
The 12 Jordanian governorates, used to validate the customer's delivery address.

Delivery itself is handled by an external delivery company at one flat fee
(the `delivery_fee_jod` store setting), so this is only name matching.
"""

from app.services.product_service import normalize_arabic_text

# Canonical Arabic name -> accepted spellings (English, common cities in that governorate)
GOVERNORATES: dict[str, tuple[str, ...]] = {
    "عمّان": ("amman", "عمان", "سحاب", "ناعور", "الجيزه", "ماركا"),
    "إربد": ("irbid", "اربد", "الرمثا", "الكوره", "بني كنانه"),
    "الزرقاء": ("zarqa", "zarqaa", "الزرقا", "الرصيفه", "الهاشميه"),
    "البلقاء": ("balqa", "السلط", "عين الباشا", "الفحيص", "ماحص", "دير علا"),
    "مادبا": ("madaba", "مأدبا"),
    "جرش": ("jerash", "jarash"),
    "عجلون": ("ajloun", "ajlun", "عنجره", "كفرنجه"),
    "المفرق": ("mafraq",),
    "الكرك": ("karak", "kerak"),
    "الطفيلة": ("tafilah", "tafila"),
    "معان": ("maan", "ma'an", "البتراء", "وادي موسى"),
    "العقبة": ("aqaba",),
}

_LOOKUP: list[tuple[str, str]] = [
    (normalize_arabic_text(alias), canonical)
    for canonical, aliases in GOVERNORATES.items()
    for alias in (canonical, *aliases)
]


def match_governorate(text: str) -> str | None:
    """Canonical governorate for a free-text name ('عمان', 'Amman', 'السلط'), else None."""
    normalized = normalize_arabic_text(text or "").strip()
    if not normalized:
        return None
    for alias, canonical in _LOOKUP:
        if normalized == alias:
            return canonical
    # "عمان - خلدا" or "الزرقاء الجديدة": the governorate name appears inside the text
    for alias, canonical in _LOOKUP:
        if len(alias) >= 3 and alias in normalized:
            return canonical
    return None
