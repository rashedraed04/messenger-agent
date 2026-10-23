"""
Store Pydantic v2 models.
"""

from datetime import datetime

from pydantic import BaseModel


class StoreBase(BaseModel):
    """Shared store fields."""
    name: str
    facebook_page_id: str | None = None
    is_active: bool = True


class StoreCreate(StoreBase):
    """Fields required to create a new store."""
    pass


class StoreRead(StoreBase):
    """Store as returned from the database."""
    id: str
    telegram_chat_id: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
