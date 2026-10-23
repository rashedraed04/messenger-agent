"""
Notification Setting Pydantic v2 models.
Manages daily report schedules, Telegram chat targets, and alert toggles.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class NotificationSettingBase(BaseModel):
    """Shared notification settings fields."""
    channel: Literal["telegram", "email", "sms"] = "telegram"
    recipient_chat_id: str | None = None
    daily_report_enabled: bool = True
    daily_report_time: str = "21:00:00"
    alert_on_new_order: bool = True
    alert_on_human_handoff: bool = True


class NotificationSettingCreate(NotificationSettingBase):
    """Payload to create notification settings for a store."""
    store_id: str


class NotificationSettingUpdate(BaseModel):
    """Payload to update notification settings."""
    recipient_chat_id: str | None = None
    daily_report_enabled: bool | None = None
    daily_report_time: str | None = None
    alert_on_new_order: bool | None = None
    alert_on_human_handoff: bool | None = None


class NotificationSettingRead(NotificationSettingBase):
    """Notification setting record read from the database."""
    id: str
    store_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
