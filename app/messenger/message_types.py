"""
Pydantic v2 models for Meta Messenger Platform webhook events and Send API.
"""

from typing import Any

from pydantic import BaseModel


class Sender(BaseModel):
    id: str


class Recipient(BaseModel):
    id: str


class QuickReply(BaseModel):
    payload: str | None = None


class IncomingMessage(BaseModel):
    mid: str
    text: str | None = None
    quick_reply: QuickReply | None = None
    attachments: list[dict[str, Any]] | None = None


class Postback(BaseModel):
    title: str | None = None
    payload: str | None = None
    mid: str | None = None


class MessagingEntry(BaseModel):
    sender: Sender
    recipient: Recipient
    timestamp: int | None = None
    message: IncomingMessage | None = None
    postback: Postback | None = None


class WebhookEntry(BaseModel):
    id: str  # Page ID
    time: int | None = None
    messaging: list[MessagingEntry] = []


class WebhookPayload(BaseModel):
    object: str
    entry: list[WebhookEntry] = []
