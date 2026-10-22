"""
Daily Report History Pydantic v2 models.
"""

from datetime import date, datetime
from pydantic import BaseModel


class ReportHistoryBase(BaseModel):
    """Shared report history fields."""
    store_id: str
    report_date: date
    report_content: str | None = None
    sent_successfully: bool = False
    error_message: str | None = None


class ReportHistoryCreate(ReportHistoryBase):
    """Fields to record a sent or attempted report."""
    pass


class ReportHistoryRead(ReportHistoryBase):
    """Report history entry as returned from the database."""
    id: str
    sent_at: datetime

    model_config = {"from_attributes": True}
