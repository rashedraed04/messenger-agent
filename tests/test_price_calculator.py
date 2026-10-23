"""
Unit tests for price calculator.
"""

from decimal import Decimal

import pytest

from app.services.price_calculator import (
    calculate_order_totals,
    format_dinar,
    format_jod,
    to_jod,
)


def test_to_jod_precision():
    assert to_jod(45) == Decimal("45.000")
    assert to_jod("45.5") == Decimal("45.500")
    assert to_jod("45.1234") == Decimal("45.123")
    assert to_jod(Decimal("10.999")) == Decimal("10.999")


def test_format_jod():
    assert format_jod(45) == "45.000 د.أ"
    assert format_jod("3.5") == "3.500 د.أ"
    assert format_jod(Decimal("0")) == "0.000 د.أ"


def test_calculate_order_totals():
    items = [
        {
            "product_id": "p1",
            "product_name": "سوفاج ديور 100 مل",
            "unit_price_jod": 45.0,
            "quantity": 1,
        },
        {
            "product_id": "p2",
            "product_name": "بلو دي شانيل 50 مل",
            "unit_price_jod": 35.0,
            "quantity": 2,
        },
    ]
    summary = calculate_order_totals(items, delivery_fee_jod=3.0, governorate="عمّان")

    assert summary.subtotal_jod == Decimal("115.000")
    assert summary.delivery_fee_jod == Decimal("3.000")
    assert summary.total_jod == Decimal("118.000")
    assert summary.governorate == "عمّان"
    assert len(summary.items) == 2
    assert summary.items[0].line_total_jod == Decimal("45.000")
    assert summary.items[1].line_total_jod == Decimal("70.000")


def test_summary_arabic_format():
    items = [
        {
            "product_id": "p1",
            "product_name": "سوفاج ديور",
            "unit_price_jod": 45.0,
            "quantity": 1,
        }
    ]
    summary = calculate_order_totals(items, delivery_fee_jod=2.0, governorate="عمّان")
    arabic_text = summary.format_arabic_summary(
        customer_name="أحمد",
        customer_phone="0791234567",
        address_detail="طبربور",
    )

    assert arabic_text == (
        "تمام يا غالي، هيك تفاصيل طلبك جاهزة للتأكيد:\n"
        "- سوفاج ديور عدد 1 (45 دينار)\n"
        "- التوصيل لـ عمّان - طبربور: 2 دينار\n"
        "المجموع كامل: 47 دينار (الدفع عند الاستلام)\n"
        "الاسم: أحمد - الرقم: 0791234567\n"
        "\n"
        "أعتمدلك الطلب؟"
    )
    for robotic in ("━━━━━━", "📱", "نعم", "!"):
        assert robotic not in arabic_text


def test_summary_keeps_fils_precision():
    items = [{"product_name": "عطر", "unit_price_jod": "12.250", "quantity": 2}]
    text = calculate_order_totals(items, delivery_fee_jod="2.5").format_arabic_summary()
    assert "(24.5 دينار)" in text
    assert "- التوصيل: 2.5 دينار" in text
    assert "المجموع كامل: 27 دينار" in text


def test_format_dinar():
    assert format_dinar(45) == "45"
    assert format_dinar("12.500") == "12.5"
    assert format_dinar("2.250") == "2.25"
    assert format_dinar("0.005") == "0.005"
    assert format_dinar(0) == "0"


def test_empty_items_raises_error():
    with pytest.raises(ValueError, match="قائمة المنتجات فارغة"):
        calculate_order_totals([])


def test_invalid_quantity_raises_error():
    items = [
        {
            "product_id": "p1",
            "product_name": "سوفاج ديور",
            "unit_price_jod": 45.0,
            "quantity": 0,
        }
    ]
    with pytest.raises(ValueError, match="غير صالحة"):
        calculate_order_totals(items)


def test_negative_price_raises_error():
    items = [
        {
            "product_id": "p1",
            "product_name": "سوفاج ديور",
            "unit_price_jod": -10.0,
            "quantity": 1,
        }
    ]
    with pytest.raises(ValueError, match="لا يمكن أن يكون سالباً"):
        calculate_order_totals(items)
