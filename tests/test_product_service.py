"""
Unit tests for ProductService fuzzy Arabic matching and stock checks.
"""

from unittest.mock import MagicMock
from app.services.product_service import ProductService, normalize_arabic_text


def test_normalize_arabic_text():
    assert normalize_arabic_text("سَوْفَاج") == "سوفاج"
    assert normalize_arabic_text("إربد") == "اربد"
    assert normalize_arabic_text("أحمد") == "احمد"
    assert normalize_arabic_text("الزرقاء") == "الزرقاء"
    assert normalize_arabic_text("وردة") == "ورده"
    assert normalize_arabic_text("Sauvage Dior") == "sauvage dior"


def test_fuzzy_match_exact_and_substring():
    mock_repo = MagicMock()
    mock_repo.get_active_catalog.return_value = [
        {
            "id": "p1",
            "name_ar": "سوفاج ديور 100 مل",
            "name_en": "Dior Sauvage",
            "brand": "Dior",
            "tags": "رجالي,فخم",
            "stock_quantity": 10,
            "in_stock": True,
            "is_active": True,
        },
        {
            "id": "p2",
            "name_ar": "بلو دي شانيل",
            "name_en": "Bleu de Chanel",
            "brand": "Chanel",
            "tags": "رجالي",
            "stock_quantity": 5,
            "in_stock": True,
            "is_active": True,
        },
    ]

    service = ProductService(mock_repo)

    # Substring match with common prefix
    match = service.match_product_by_name("s1", "بدي عطر سوفاج")
    assert match is not None
    assert match["id"] == "p1"

    # English query
    match_en = service.match_product_by_name("s1", "Bleu de Chanel")
    assert match_en is not None
    assert match_en["id"] == "p2"

    # Partial brand / arabic token
    match_partial = service.match_product_by_name("s1", "شانيل")
    assert match_partial is not None
    assert match_partial["id"] == "p2"

    # Non-existent
    match_none = service.match_product_by_name("s1", "عطر غير موجود أبدا")
    assert match_none is None


def test_availability_check_ignores_quantities():
    mock_repo = MagicMock()
    mock_repo.get_by_id.return_value = {"id": "p1", "name_ar": "مسبحة", "is_active": True}
    service = ProductService(mock_repo)
    assert service.check_available("s1", "p1")[0] is True

    mock_repo.get_by_id.return_value = {"id": "p1", "name_ar": "مسبحة", "is_active": False}
    assert service.check_available("s1", "p1")[0] is False

    mock_repo.get_by_id.return_value = None
    assert service.check_available("s1", "p1")[0] is False
