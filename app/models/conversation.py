"""
Conversation and Message Pydantic v2 models.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    """Conversation state machine states."""
    DISCOVERY = "DISCOVERY"
    PRODUCT_SELECTION = "PRODUCT_SELECTION"
    COLLECTING_DETAILS = "COLLECTING_DETAILS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    HUMAN_HANDOFF = "HUMAN_HANDOFF"


class MessageDirection(str, Enum):
    """Message direction."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ConversationBase(BaseModel):
    """Shared conversation fields."""
    messenger_psid: str
    state: ConversationState = ConversationState.DISCOVERY
    collected_slots: dict[str, Any] = Field(default_factory=dict)
    current_order_id: str | None = None
    is_human_handoff: bool = False
    handoff_reason: str | None = None


class ConversationRead(ConversationBase):
    """Conversation as returned from the database."""
    id: str
    store_id: str
    customer_id: str | None = None
    last_message_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageBase(BaseModel):
    """Shared message fields."""
    direction: MessageDirection
    content: str
    message_type: str = "text"
    ai_metadata: dict[str, Any] | None = None


class MessageCreate(MessageBase):
    """Fields to create a message."""
    conversation_id: str


class MessageRead(MessageBase):
    """Message as returned from the database."""
    id: str
    conversation_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
