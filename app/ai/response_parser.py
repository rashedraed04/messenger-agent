"""
Robust parser for structured AI JSON responses with markdown and error recovery.
"""

import json
import re
from typing import Any
from app.ai.provider_interface import AIResponse


def extract_json_block(text: str) -> str:
    """Extract JSON object from string even if wrapped in markdown code blocks."""
    text = text.strip()

    # Case 1: Markdown code block ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Case 2: Outermost curly braces { ... }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace : last_brace + 1].strip()

    return text


def parse_ai_response(
    raw_text: str,
    model_name: str = "gemini-2.5-flash",
    latency_ms: float = 0.0,
) -> AIResponse:
    """
    Parse the AI output into a structured AIResponse object.
    Falls back gracefully if the output is plain text or invalid JSON.
    """
    cleaned_json_str = extract_json_block(raw_text)

    try:
        data = json.loads(cleaned_json_str)
        if isinstance(data, dict):
            return AIResponse(
                response_text=str(data.get("response_text") or "").strip(),
                extracted_slots=data.get("extracted_slots") or {},
                intent=str(data.get("intent") or "general_inquiry"),
                suggested_state=data.get("suggested_state"),
                customer_angry=str(data.get("customer_mood") or "").strip().lower() == "angry",
                raw_response=raw_text,
                model_name=model_name,
                latency_ms=latency_ms,
            )
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: Entire text is response_text
    # Strip any accidental backticks or json tags
    fallback_text = re.sub(r"```(?:json)?|```", "", raw_text).strip()
    return AIResponse(
        response_text=fallback_text,
        extracted_slots={},
        intent="general_inquiry",
        suggested_state=None,
        raw_response=raw_text,
        model_name=model_name,
        latency_ms=latency_ms,
    )
