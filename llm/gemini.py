"""Gemini client (Flash Lite) with JSON structured output."""

from __future__ import annotations

import json
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from config.settings import settings

T = TypeVar("T", bound=BaseModel)


class GeminiError(RuntimeError):
    pass


def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise GeminiError("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=settings.gemini_api_key)


def generate_json(prompt: str, schema: type[T], *, temperature: float = 0.4) -> T:
    """Call Gemini and parse the response into a Pydantic model."""
    client = _client()
    config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="application/json",
        response_schema=schema,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:  # noqa: BLE001 — surface API errors to caller
        raise GeminiError(str(exc)) from exc

    text = (response.text or "").strip()
    if not text:
        raise GeminiError("Empty response from Gemini.")
    try:
        return schema.model_validate_json(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Invalid JSON from Gemini: {text[:200]}") from exc
