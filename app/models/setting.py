"""
Store Setting Pydantic v2 models.
"""

from datetime import datetime

from pydantic import BaseModel


class StoreSettingBase(BaseModel):
    """Shared store setting fields."""
    setting_key: str
    setting_value: str | None = None
    setting_type: str = "text"


class StoreSettingUpdate(BaseModel):
    """Fields to update a setting value."""
    setting_value: str | None = None


class StoreSettingRead(StoreSettingBase):
    """Store setting as returned from the database."""
    id: str
    store_id: str
    updated_at: datetime

    model_config = {"from_attributes": True}
