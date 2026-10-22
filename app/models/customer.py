"""
Customer Pydantic v2 models.
"""

from datetime import datetime

from pydantic import BaseModel


class CustomerRead(BaseModel):
    """Customer as returned from the database."""
    id: str
    store_id: str
    messenger_psid: str
    name: str | None = None
    phone_normalized: str | None = None
    governorate: str | None = None
    address_detail: str | None = None
    total_orders: int = 0
    first_contact_at: datetime
    last_contact_at: datetime

    model_config = {"from_attributes": True}
