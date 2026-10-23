"""
Abstract interface for AI Providers.

Decouples the conversation engine from specific LLM vendors (Gemini, OpenAI, Anthropic, etc.).
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ImageInput(BaseModel):
    """An image passed to the model alongside the customer's message."""
    data: bytes
    mime_type: str
    # Text placed just before the image (e.g. which catalog product it shows)
    label: str | None = None
    source_url: str | None = None


class AIResponse(BaseModel):
    """Normalized response returned by any AI provider."""
    response_text: str = ""
    extracted_slots: dict[str, Any] = Field(default_factory=dict)
    intent: str = "general_inquiry"
    suggested_state: str | None = None
    customer_angry: bool = False
    raw_response: str = ""
    model_name: str = ""
    latency_ms: float = 0.0
    tokens_used: int = 0


class AIProvider(ABC):
    """Interface for generative AI providers."""

    @abstractmethod
    async def generate_response(
        self,
        system_instruction: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        timeout_seconds: float = 10.0,
        images: list[ImageInput] | None = None,
    ) -> AIResponse:
        """
        Generate a conversational response and extract order slots.

        Args:
            system_instruction: Dynamic prompt containing catalog, rules, tone, and schema.
            user_message: The customer's incoming message text.
            conversation_history: Past turns formatted as [{'role': 'user'|'model', 'content': '...'}].
            timeout_seconds: Maximum time to wait before timing out.
            images: Images attached to the current message, in order (catalog
                reference photos first, then what the customer sent).

        Returns:
            AIResponse with parsed structured output and metadata.
        """
        pass
