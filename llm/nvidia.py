"""NVIDIA hosted models (build.nvidia.com) through their OpenAI-compatible chat API, over httpx."""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from config.settings import settings

T = TypeVar("T", bound=BaseModel)

_THINK = re.compile(r"<think>.*?</think>", re.S)


class NvidiaError(RuntimeError):
    """``key_rejected``: the API key itself was refused (401/403), so no NVIDIA model will answer."""

    def __init__(self, message: str, *, key_rejected: bool = False) -> None:
        super().__init__(message)
        self.key_rejected = key_rejected


def json_text(content: str) -> str:
    """A model reply as bare JSON: without a reasoning block or code fences, outermost object only."""
    text = _THINK.sub("", content or "").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text


def chat(
    model: str,
    messages: list[dict[str, Any]],
    *,
    temperature: float,
    schema: type[BaseModel] | None = None,
    max_tokens: int = 8192,
) -> str:
    """One chat completion; returns the reply text. Raises NvidiaError on any failure."""
    body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if schema is not None:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
    res = _post(model, body)
    if res.status_code in (400, 422) and schema is not None:
        # Some hosted models refuse response_format; the schema is in the prompt too, so ask plainly.
        body.pop("response_format")
        res = _post(model, body)
    if res.status_code != 200:
        raise NvidiaError(f"NVIDIA {model}: HTTP {res.status_code} {res.text[:200]}", key_rejected=res.status_code in (401, 403))
    try:
        return res.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise NvidiaError(f"NVIDIA {model}: unexpected reply {res.text[:200]}") from exc


def _post(model: str, body: dict[str, Any]) -> httpx.Response:
    try:
        return httpx.post(
            f"{settings.nvidia_base_url}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {settings.nvidia_api_key}", "Accept": "application/json"},
            timeout=settings.nvidia_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise NvidiaError(f"NVIDIA {model}: {type(exc).__name__} {exc}") from exc


def generate_json(model: str, prompt: str, schema: type[T], *, temperature: float) -> T:
    """Ask one NVIDIA model for JSON matching ``schema``."""
    shaped = (
        f"{prompt}\n\nReply with one JSON object only, no prose, matching this JSON schema:\n"
        f"{json.dumps(schema.model_json_schema())}"
    )
    text = chat(model, [{"role": "user", "content": shaped}], temperature=temperature, schema=schema)
    try:
        return schema.model_validate_json(json_text(text))
    except ValidationError as exc:
        raise NvidiaError(f"NVIDIA {model}: reply did not match {schema.__name__}: {text[:200]}") from exc
