"""
Product Pydantic v2 models.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class ProductBase(BaseModel):
    """Shared product fields."""
    name_ar: str
    name_en: str | None = None
    description_ar: str | None = None
    brand: str | None = None
    size_ml: str | None = None
    price_jod: Decimal = Field(..., ge=0, decimal_places=3)
    is_active: bool = True
    image_url: str | None = None
    category: str | None = None
    product_type: str | None = None
    tags: str | None = None
    sort_order: int = 0


class ProductCreate(ProductBase):
    """Fields required to create a new product."""
    store_id: str


class ProductUpdate(BaseModel):
    """Fields that can be updated on a product."""
    name_ar: str | None = None
    name_en: str | None = None
    description_ar: str | None = None
    brand: str | None = None
    size_ml: str | None = None
    price_jod: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    image_url: str | None = None
    category: str | None = None
    product_type: str | None = None
    tags: str | None = None
    sort_order: int | None = None


class ProductRead(ProductBase):
    """Product as returned from the database."""
    id: str
    store_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
