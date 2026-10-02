"""
LLM access for AWDAX: NVIDIA hosted models first, Gemini as fallback.

Pattern ported (to `requests`) from the owner's feat/nvidia-llm branch:
awdax/Backend/llm/nvidia.py and llm/gemini.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Callable

import requests

logger = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.S)
_DEFAULT_BASE = "https://integrate.api.nvidia.com/v1"
_DEFAULT_MODELS = (
    "nvidia/nemotron-3-ultra-550b-a55b,"
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning,"
    "nvidia/nemotron-3.5-lightning-30b-a3b,"
    "nvidia/nemotron-3-super-120b-a12b"
)
_NO_KEY = "No LLM key set: add NVIDIA_API_KEY (or GEMINI_API_KEY) to .env"

# Process-wide: once NVIDIA refuses the key (401/403) we stop calling it.
_nvidia_key_rejected = False


def _key(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    return "" if v.startswith("your_") else v


def _nvidia_models() -> list[str]:
    names = []
    first = (os.getenv("LLM_MODEL") or "").strip()
    if first:
        names.append(first)
    names += [m.strip() for m in (os.getenv("NVIDIA_MODELS") or _DEFAULT_MODELS).split(",")]
    out: list[str] = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def _strip_think(text: str) -> str:
    return _THINK.sub("", text or "").strip()


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _parse_json(text: str) -> Any:
    text = _strip_fences(_strip_think(text))
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        close = "}" if text[start] == "{" else "]"
        end = text.rfind(close)
        if end > start:
            text = text[start : end + 1]
    return json.loads(text)


def _nvidia_call(prompt: str, temperature: float, parse: Callable[[str], Any]) -> Any:
    """Try each NVIDIA model in order. Raises RuntimeError (no key text) when all fail."""
    global _nvidia_key_rejected
    base = (os.getenv("NVIDIA_API_BASE") or os.getenv("NVIDIA_BASE_URL") or _DEFAULT_BASE).strip().rstrip("/")
    try:
        timeout = float(os.getenv("NVIDIA_TIMEOUT_SECONDS") or 90)
    except ValueError:
        timeout = 90.0
    headers = {"Authorization": f"Bearer {_key('NVIDIA_API_KEY')}", "Accept": "application/json"}
    last = "no NVIDIA model answered"
    for model in _nvidia_models():
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": 8192,
        }
        try:
            res = requests.post(f"{base}/chat/completions", json=body, headers=headers, timeout=timeout)
            if res.status_code in (401, 403):
                _nvidia_key_rejected = True
                raise RuntimeError(f"NVIDIA key rejected (HTTP {res.status_code})")
            if res.status_code != 200:
                raise RuntimeError(f"NVIDIA {model}: HTTP {res.status_code}")
            content = res.json()["choices"][0]["message"]["content"] or ""
            return parse(content)
        except Exception as exc:  # noqa: BLE001 - every failure moves on to the next model
            last = f"{type(exc).__name__}: {exc}"
            logger.warning("NVIDIA model %s failed: %s", model, last)
            if _nvidia_key_rejected:
                break
    raise RuntimeError(f"NVIDIA request failed ({last})")


def _gemini_text(prompt: str, temperature: float) -> str:
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai is not installed") from exc
    genai.configure(api_key=_key("GEMINI_API_KEY"))
    model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    resp = model.generate_content(prompt)
    return (resp.text or "").strip()


def _run(prompt: str, temperature: float, parse: Callable[[str], Any]) -> Any:
    has_nvidia = bool(_key("NVIDIA_API_KEY")) and not _nvidia_key_rejected
    has_gemini = bool(_key("GEMINI_API_KEY"))
    if not has_nvidia and not has_gemini:
        if _nvidia_key_rejected:
            raise RuntimeError("NVIDIA key rejected and no GEMINI_API_KEY set")
        raise RuntimeError(_NO_KEY)
    if has_nvidia:
        try:
            return _nvidia_call(prompt, temperature, parse)
        except RuntimeError:
            if not has_gemini:
                raise
            logger.warning("NVIDIA unavailable; falling back to Gemini")
    return parse(_gemini_text(prompt, temperature))


def llm_json(prompt: str, *, temperature: float = 0.2) -> Any:
    return _run(prompt, temperature, _parse_json)


def llm_text(prompt: str, *, temperature: float = 0.2) -> str:
    return _run(prompt, temperature, lambda t: _strip_think(t))


def llm_available() -> bool:
    return bool(_key("GEMINI_API_KEY") or (_key("NVIDIA_API_KEY") and not _nvidia_key_rejected))
