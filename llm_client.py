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
import time
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
# A model that timed out or answered busy (429/5xx) waits out a cooldown, and the model that last answered
# goes first, so one slow model doesn't cost a full timeout on every call (as on feat/nvidia-llm).
_cooldown_until: dict[str, float] = {}
_last_good: str | None = None


def _cooldown_seconds() -> float:
    try:
        return float(os.getenv("NVIDIA_COOLDOWN_SECONDS") or 300)
    except ValueError:
        return 300.0


def _ordered(models: list[str], now: float) -> list[str]:
    """Healthy models first (the last one that answered leads), models in cooldown last as a final resort."""
    healthy = [m for m in models if _cooldown_until.get(m, 0) <= now]
    cooling = [m for m in models if m not in healthy]
    if _last_good in healthy:
        healthy.remove(_last_good)
        healthy.insert(0, _last_good)
    return healthy + cooling


def _key(name: str) -> str:
    v = (os.getenv(name) or "").strip()
    return "" if v.startswith("your_") else v


def _model_name(name: str) -> str:
    """LiteLLM-style "openai/<org>/<model>" names carry a provider prefix NVIDIA's API rejects (404).
    Keep real NVIDIA ids that start with openai/, such as "openai/gpt-oss-120b"."""
    name = name.strip()
    if name.startswith("openai/") and "/" in name[len("openai/"):]:
        return name[len("openai/"):]
    return name


def _nvidia_models() -> list[str]:
    names = []
    first = (os.getenv("LLM_MODEL") or "").strip()
    if first:
        names.append(first)
    names += [m.strip() for m in (os.getenv("NVIDIA_MODELS") or _DEFAULT_MODELS).split(",")]
    out: list[str] = []
    for n in map(_model_name, names):
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
    global _nvidia_key_rejected, _last_good
    base =(os.getenv("NVIDIA_API_BASE") or os.getenv("NVIDIA_BASE_URL") or _DEFAULT_BASE).strip().rstrip("/")
    try:
        timeout = float(os.getenv("NVIDIA_TIMEOUT_SECONDS") or 90)
    except ValueError:
        timeout = 90.0
    headers = {"Authorization": f"Bearer {_key('NVIDIA_API_KEY')}", "Accept": "application/json"}
    last = "no NVIDIA model answered"
    for model in _ordered(_nvidia_models(), time.monotonic()):
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
                if res.status_code == 429 or res.status_code >= 500:
                    _cooldown_until[model] = time.monotonic() + _cooldown_seconds()
                raise RuntimeError(f"NVIDIA {model}: HTTP {res.status_code}")
            content = res.json()["choices"][0]["message"]["content"] or ""
            result = parse(content)
            _last_good = model
            _cooldown_until.pop(model, None)
            return result
        except Exception as exc:  # noqa: BLE001 - every failure moves on to the next model
            if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                _cooldown_until[model] = time.monotonic() + _cooldown_seconds()
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
