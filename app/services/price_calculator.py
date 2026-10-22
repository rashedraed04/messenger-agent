"""
Price calculation engine for store orders (JOD).

All financial calculations MUST use Python's Decimal type with 3 decimal places
(Jordanian Dinar fils: 1 JOD = 1000 fils).
AI MUST NEVER perform financial calculations.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from pydantic import BaseModel, Field

JOD_PRECISION = Decimal("0.001")


def to_jod(value: float | int | str | Decimal) -> Decimal:
    """Convert any numeric input to a Decimal with exactly 3 decimal places."""
    if isinstance(value, Decimal):
        return value.quantize(JOD_PRECISION, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(JOD_PRECISION, rounding=ROUND_HALF_UP)


def format_jod(value: Decimal | float | int | str) -> str:
    """Format a JOD decimal as Arabic string: '45.000 د.أ'."""
    val = to_jod(value)
    return f"{val:.3f} د.أ"


def format_dinar(value: Decimal | float | int | str) -> str:
    """Format a JOD amount the way people write it in chat: '45', '12.5', '2.25'."""
    val = to_jod(value)
    text = f"{val:.3f}".rstrip("0").rstrip(".")
    return text or "0"


class CalculatedItem(BaseModel):
    """Calculated item ready for display and database snapshot."""
    product_id: str | None = None
    product_name: str
    unit_price_jod: Decimal
    quantity: int
    line_total_jod: Decimal


class OrderPriceSummary(BaseModel):
    """Complete financial breakdown of an order."""
    items: list[CalculatedItem]
    subtotal_jod: Decimal
    delivery_fee_jod: Decimal
    total_jod: Decimal
    governorate: str | None = None

    def format_arabic_summary(
        self,
        customer_name: str | None = None,
        customer_phone: str | None = None,
        address_detail: str | None = None,
    ) -> str:
        """
        Generate the order summary as a natural chat message from the shop owner.
        All amounts come from the Decimal fields computed here, never from the AI.
        """
        lines = ["تمام يا غالي، هيك تفاصيل طلبك جاهزة للتأكيد:"]
        for it in self.items:
            lines.append(
                f"- {it.product_name} عدد {it.quantity} ({format_dinar(it.line_total_jod)} دينار)"
            )

        place = " - ".join(p for p in (self.governorate, address_detail) if p)
        place_text = f" لـ {place}" if place else ""
        lines.append(f"- التوصيل{place_text}: {format_dinar(self.delivery_fee_jod)} دينار")
        lines.append(
            f"المجموع كامل: {format_dinar(self.total_jod)} دينار (الدفع عند الاستلام)"
        )

        contact = []
        if customer_name:
            contact.append(f"الاسم: {customer_name}")
        if customer_phone:
            contact.append(f"الرقم: {customer_phone}")
        if contact:
            lines.append(" - ".join(contact))

        lines.append("\nأعتمدلك الطلب؟")
        return "\n".join(lines)


def calculate_order_totals(
    items_data: list[dict[str, Any]],
    delivery_fee_jod: float | Decimal | str = 0,
    governorate: str | None = None,
) -> OrderPriceSummary:
    """
    Calculate subtotal, delivery fee, and grand total.

    Args:
        items_data: List of dicts, each with:
            - 'product_id': Optional product ID
            - 'product_name': Name of product
            - 'unit_price_jod': Unit price in JOD
            - 'quantity': Positive integer
        delivery_fee_jod: The store's flat delivery fee
        governorate: Optional name of the governorate

    Returns:
        OrderPriceSummary containing calculated items and totals with 3 decimal places.

    Raises:
        ValueError: If quantity <= 0 or price < 0 or items list is empty.
    """
    if not items_data:
        raise ValueError("قائمة المنتجات فارغة")

    calculated_items: list[CalculatedItem] = []
    subtotal = Decimal("0.000")

    for raw in items_data:
        raw_qty = raw.get("quantity")
        qty = int(raw_qty) if raw_qty is not None else 1
        if qty <= 0:
            raise ValueError(f"كمية المنتج '{raw.get('product_name')}' غير صالحة ({qty})")

        unit_price = to_jod(raw.get("unit_price_jod", 0))
        if unit_price < 0:
            raise ValueError(f"سعر المنتج '{raw.get('product_name')}' لا يمكن أن يكون سالباً")

        line_total = to_jod(unit_price * qty)
        subtotal += line_total

        calculated_items.append(
            CalculatedItem(
                product_id=raw.get("product_id"),
                product_name=raw.get("product_name") or "منتج",
                unit_price_jod=unit_price,
                quantity=qty,
                line_total_jod=line_total,
            )
        )

    fee = to_jod(delivery_fee_jod)
    total = to_jod(subtotal + fee)

    return OrderPriceSummary(
        items=calculated_items,
        subtotal_jod=subtotal,
        delivery_fee_jod=fee,
        total_jod=total,
        governorate=governorate,
    )
