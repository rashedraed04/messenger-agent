"""
Order and OrderItem Pydantic v2 models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    """Order states; delivery itself is tracked by the external delivery company."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class OrderItemBase(BaseModel):
    """A single line item in an order."""
    product_id: str | None = None
    product_name_snapshot: str
    unit_price_snapshot: Decimal = Field(..., decimal_places=3)
    quantity: int = Field(..., gt=0)
    line_total_jod: Decimal = Field(..., decimal_places=3)


class OrderItemCreate(OrderItemBase):
    """Create a new order item."""
    order_id: str


class OrderItemRead(OrderItemBase):
    """Order item as returned from the database."""
    id: str

    model_config = {"from_attributes": True}


class OrderBase(BaseModel):
    """Shared order fields."""
    store_id: str
    order_number: str
    status: OrderStatus = OrderStatus.PENDING
    customer_name: str | None = None
    customer_phone: str | None = None
    governorate: str | None = None
    address_detail: str | None = None
    subtotal_jod: Decimal = Field(default=Decimal("0.000"), decimal_places=3)
    delivery_fee_jod: Decimal = Field(default=Decimal("0.000"), decimal_places=3)
    total_jod: Decimal = Field(default=Decimal("0.000"), decimal_places=3)
    notes: str | None = None
    cancellation_reason: str | None = None


class OrderCreate(OrderBase):
    """Fields required to create a new order."""
    customer_id: str | None = None
    conversation_id: str | None = None


class OrderRead(OrderBase):
    """Order as returned from the database."""
    id: str
    customer_id: str | None = None
    conversation_id: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemRead] = []

    model_config = {"from_attributes": True}
