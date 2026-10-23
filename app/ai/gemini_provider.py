"""
Gemini AI Provider implementation using google-genai SDK.
"""

import asyncio
import logging
import time

from google import genai
from google.genai import errors, types

from app.ai.provider_interface import AIProvider, AIResponse, ImageInput
from app.ai.response_parser import parse_ai_response

logger = logging.getLogger(__name__)


def build_chat_turns(
    conversation_history: list[dict[str, str]], user_message: str
) -> list[tuple[str, str]]:
    """
    Convert history + current message into alternating (role, text) turns.

    Gemini expects user/model turns to alternate and the chat to open with a
    user turn, so leading model turns are dropped, consecutive same-role
    messages are merged, and empty messages are skipped.
    """
    turns: list[tuple[str, str]] = []
    for turn in [*conversation_history, {"role": "user", "content": user_message}]:
        text = (turn.get("content") or "").strip()
        if not text:
            continue
        role = "user" if turn.get("role") == "user" else "model"
        if not turns and role == "model":
            continue
        if turns and turns[-1][0] == role:
            turns[-1] = (role, f"{turns[-1][1]}\n{text}")
        else:
            turns.append((role, text))
    return turns


class GeminiProvider(AIProvider):
    """Google Gemini AI implementation with retry and automatic fallback."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.5-flash",
        fallback_models: list[str] | None = None,
    ):
        self.api_key = api_key
        self.model_name = model_name
        # No lite models: they translate Fusha literally and sound robotic
        self.fallback_models = fallback_models or [
            "gemini-3.6-flash",
            "gemini-3.8-flash",
        ]
        self.client = genai.Client(api_key=api_key) if api_key else None

    async def generate_response(
        self,
        system_instruction: str,
        user_message: str,
        conversation_history: list[dict[str, str]] | None = None,
        timeout_seconds: float = 30.0,
        images: list[ImageInput] | None = None,
    ) -> AIResponse:
        """
        Call Gemini API asynchronously with instant fallback on 503 high-demand.
        """
        start_time = time.perf_counter()

        if not self.client or not self.api_key:
            logger.warning("GeminiProvider: No API key configured, returning fallback response")
            return AIResponse(
                response_text="هلا والله، ثواني وبرجعلك.",
                model_name=self.model_name,
                latency_ms=0.0,
            )

        # Build message contents (chronological history, then the current message)
        turns = build_chat_turns(conversation_history or [], user_message)
        contents = [
            types.Content(role=role, parts=[types.Part.from_text(text=text)])
            for role, text in turns
        ]
        if images and contents:
            # The current message is always the last (user) turn
            for image in images:
                if image.label:
                    contents[-1].parts.append(types.Part.from_text(text=image.label))
                contents[-1].parts.append(
                    types.Part.from_bytes(data=image.data, mime_type=image.mime_type)
                )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.5,
            response_mime_type="application/json",
        )

        models_to_try = [self.model_name]
        for fb in self.fallback_models:
            if fb not in models_to_try:
                models_to_try.append(fb)

        last_error = None

        for current_model in models_to_try:
            # Check overall timeout
            elapsed = time.perf_counter() - start_time
            if elapsed >= timeout_seconds - 3.0:
                logger.warning("Overall timeout budget reached before trying %s", current_model)
                break

            per_model_timeout = min(15.0, timeout_seconds - elapsed)

            try:
                call_coro = self.client.aio.models.generate_content(
                    model=current_model,
                    contents=contents,
                    config=config,
                )
                response = await asyncio.wait_for(call_coro, timeout=per_model_timeout)

                latency_ms = (time.perf_counter() - start_time) * 1000
                raw_text = response.text or ""

                parsed = parse_ai_response(
                    raw_text=raw_text,
                    model_name=current_model,
                    latency_ms=latency_ms,
                )
                return parsed

            except TimeoutError:
                logger.warning("Gemini model %s timed out after %.1fs. Trying next fallback...", current_model, per_model_timeout)
                last_error = "timeout"
                continue

            except (errors.ServerError, errors.APIError, Exception) as e:
                last_error = e
                logger.warning(
                    "Gemini model %s error (%s). Switching immediately to next fallback...",
                    current_model,
                    e,
                )
                continue

        latency_ms = (time.perf_counter() - start_time) * 1000
        if last_error == "timeout":
            logger.error("Gemini API all attempts timed out")
            return AIResponse(
                response_text="معلش تأخرت عليك شوي، ممكن تبعث رسالتك كمان مرة؟",
                intent="timeout",
                model_name=self.model_name,
                latency_ms=latency_ms,
            )

        logger.error("Gemini API all fallback models exhausted. Last error: %s", last_error)
        return AIResponse(
            response_text="معلش في ضغط عنا هسا، ابعث رسالتك كمان مرة، وإذا بتحب بخلي حدا من الشباب يحكي معك.",
            intent="error",
            model_name=self.model_name,
            latency_ms=latency_ms,
        )
