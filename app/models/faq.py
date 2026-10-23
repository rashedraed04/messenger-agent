"""
FAQ Pydantic v2 models.
"""

from datetime import datetime

from pydantic import BaseModel


class FAQBase(BaseModel):
    """Shared FAQ fields."""
    question_ar: str
    answer_ar: str
    is_active: bool = True
    sort_order: int = 0


class FAQCreate(FAQBase):
    """Fields to create a new FAQ."""
    store_id: str


class FAQUpdate(BaseModel):
    """Fields to update an existing FAQ."""
    question_ar: str | None = None
    answer_ar: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class FAQRead(FAQBase):
    """FAQ as returned from the database."""
    id: str
    store_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
