"""Gemini client (Flash Lite) with JSON structured output."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from config.settings import settings

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    pass


def _candidate_models() -> list[str]:
    """The configured model first, then the fallbacks, without repeats."""
    return list(dict.fromkeys(m for m in (settings.gemini_model, *settings.gemini_fallback_models) if m))


def _worth_another_model(exc: Exception) -> bool:
    """Overloaded or failing (5xx), this model's quota used up (429) or model retired (404).
    A bad request or a bad key (other 4xx) fails the same way on every model."""
    if isinstance(exc, genai_errors.ServerError):
        return True
    return isinstance(exc, genai_errors.ClientError) and exc.code in (404, 429)


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
    models = _candidate_models()
    for i, model in enumerate(models):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
            break
        except Exception as exc:  # noqa: BLE001 — surface API errors to caller
            if i == len(models) - 1 or not _worth_another_model(exc):
                raise GeminiError(str(exc)) from exc
            logger.warning("Gemini %s unavailable (%s); trying %s.", model, str(exc)[:80], models[i + 1])

    text = (response.text or "").strip()
    if not text:
        raise GeminiError("Empty response from Gemini.")
    try:
        return schema.model_validate_json(text)
    except json.JSONDecodeError as exc:
        raise GeminiError(f"Invalid JSON from Gemini: {text[:200]}") from exc
