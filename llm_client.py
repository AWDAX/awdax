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
# Models whose cooldown came from a timeout. Busy answers (429/5xx) come back at once, so a busy model is a cheap last
# resort; a timed-out one costs a full timeout, so a call tries at most one of those (the one cooling longest).
_timed_out: set[str] = set()
_last_good: str | None = None


def _cooldown_seconds() -> float:
    try:
        return float(os.getenv("NVIDIA_COOLDOWN_SECONDS") or 300)
    except ValueError:
        return 300.0


def _ordered(models: list[str], now: float) -> list[str]:
    """Healthy models first (the last one that answered leads), busy ones as a last resort, then at most one that
    timed out, so a call with every model degraded waits out one timeout rather than one per model."""
    healthy = [m for m in models if _cooldown_until.get(m, 0) <= now]
    cooling = [m for m in models if m not in healthy]
    busy = [m for m in cooling if m not in _timed_out]
    slow = sorted((m for m in cooling if m in _timed_out), key=lambda m: _cooldown_until.get(m, 0))
    if _last_good in healthy:
        healthy.remove(_last_good)
        healthy.insert(0, _last_good)
    return healthy + busy + slow[:1]


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


def _salvage_json(text: str) -> Any:
    """JSON the model's output limit cut off mid-list ({"rows": [{...}, {...}, {"na): the complete objects before the cut,
    with the open brackets closed. Better than losing every row of a long page because the last one was unfinished."""
    ends = [m.start() for m in re.finditer(r"\}", text)][-400:]
    for pos in reversed(ends):
        head = text[: pos + 1]
        for closer in ("", "]", "]}", "}", "}]"):
            try:
                return json.loads(head + closer)
            except ValueError:
                continue
    raise ValueError("no complete JSON in the answer")


def _parse_json(text: str) -> Any:
    text = _strip_fences(_strip_think(text))
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        close = "}" if text[start] == "{" else "]"
        end = text.rfind(close)
        if end > start:
            text = text[start : end + 1]
    try:
        return json.loads(text)
    except ValueError:
        if not starts:
            raise
        # Cut off before its closing bracket: keep what is complete (see _salvage_json). The caller still checks its shape.
        return _salvage_json(text)


def _nvidia_call(prompt: str, temperature: float, parse: Callable[[str], Any], deadline: float | None = None) -> Any:
    """Try each NVIDIA model in order, stopping at `deadline` (time.monotonic()) when given. Raises RuntimeError
    (no key text) when all fail."""
    global _nvidia_key_rejected, _last_good
    base =(os.getenv("NVIDIA_API_BASE") or _DEFAULT_BASE).strip().rstrip("/")
    try:
        timeout = float(os.getenv("NVIDIA_TIMEOUT_SECONDS") or 90)
    except ValueError:
        timeout = 90.0
    headers = {"Authorization": f"Bearer {_key('NVIDIA_API_KEY')}", "Accept": "application/json"}
    last = "no NVIDIA model answered"
    for model in _ordered(_nvidia_models(), time.monotonic()):
        if deadline is not None:
            left = deadline - time.monotonic()
            if left < 1:
                last = "out of time"
                break
            timeout = min(timeout, left)
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
                    _timed_out.discard(model)
                raise RuntimeError(f"NVIDIA {model}: HTTP {res.status_code}")
            content = res.json()["choices"][0]["message"]["content"] or ""
            result = parse(content)
            _last_good = model
            _cooldown_until.pop(model, None)
            _timed_out.discard(model)
            return result
        except Exception as exc:  # noqa: BLE001 - every failure moves on to the next model
            if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
                _cooldown_until[model] = time.monotonic() + _cooldown_seconds()
                if isinstance(exc, requests.Timeout):
                    _timed_out.add(model)
            last = f"{type(exc).__name__}: {exc}"
            logger.warning("NVIDIA model %s failed: %s", model, last)
            if _nvidia_key_rejected:
                break
    raise RuntimeError(f"NVIDIA request failed ({last})")


DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
# Follows Google's current flash model. A pinned name stops working the day Google retires it (gemini-2.0-flash did), so a
# model that has gone falls back to this instead of failing every run.
FALLBACK_GEMINI_MODEL = "gemini-flash-latest"
GEMINI_TIMEOUT_S = 90.0


def _model_gone(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return "notfound" in text or "no longer available" in text or "is not found" in text or "404" in text


_BUSY_WORDS = ("deadlineexceeded", "serviceunavailable", "resourceexhausted", "toomanyrequests", "internalservererror",
               "overloaded", "timed out", "timeout", "429", "500", "502", "503", "504")


def _model_busy(exc: Exception) -> bool:
    """Gemini answered "busy", overloaded or out of time: worth asking again a moment later (a retired model is not)."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(w in text for w in _BUSY_WORDS)


def _gemini_attempts() -> int:
    try:
        return max(1, int(os.getenv("GEMINI_ATTEMPTS", "3")))
    except ValueError:
        return 3


def _gemini_text(prompt: str, temperature: float, *, json_mode: bool = False, timeout: float | None = None) -> str:
    """One Gemini answer. Every failure is a RuntimeError, like the NVIDIA path, so callers can treat "the model is
    unavailable" as one thing."""
    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai is not installed") from exc
    genai.configure(api_key=_key("GEMINI_API_KEY"))
    chosen = (os.getenv("GEMINI_MODEL") or "").strip() or DEFAULT_GEMINI_MODEL
    names = [chosen] if chosen == FALLBACK_GEMINI_MODEL else [chosen, FALLBACK_GEMINI_MODEL]
    last: Exception | None = None
    for name in names:
        config: dict[str, Any] = {}
        # Google: keep temperature at its default (1.0) on Gemini 3 models; below that they can loop or degrade.
        if not name.startswith("gemini-3") and name != FALLBACK_GEMINI_MODEL:
            config["temperature"] = temperature
        if json_mode:
            config["response_mime_type"] = "application/json"
        gone = False
        for attempt in range(1, _gemini_attempts() + 1):
            try:
                model = genai.GenerativeModel(name, generation_config=config or None)
                resp = model.generate_content(prompt, request_options={"timeout": timeout or GEMINI_TIMEOUT_S})
                return (resp.text or "").strip()  # raises ValueError when the answer was blocked or empty
            except Exception as exc:  # noqa: BLE001 - provider errors vary; the caller only needs "unavailable" and why
                last = exc
                gone = _model_gone(exc)
                if gone or not _model_busy(exc) or attempt >= _gemini_attempts():
                    break
                wait = 2.0 * attempt  # busy or out of time: a short, growing pause, then ask again
                logger.warning("Gemini busy (%s); asking again in %.0f s (attempt %d)", type(exc).__name__, wait, attempt + 1)
                time.sleep(wait)
        if not gone:
            break
        logger.warning("Gemini model %s is gone (%s); trying %s", name, last, FALLBACK_GEMINI_MODEL)
    raise RuntimeError(f"Gemini request failed ({type(last).__name__}: {str(last)[:200]})") from last


def _run(prompt: str, temperature: float, parse: Callable[[str], Any], deadline: float | None = None, json_mode: bool = False) -> Any:
    has_nvidia = bool(_key("NVIDIA_API_KEY")) and not _nvidia_key_rejected
    has_gemini = bool(_key("GEMINI_API_KEY"))
    if not has_nvidia and not has_gemini:
        if _nvidia_key_rejected:
            raise RuntimeError("NVIDIA key rejected and no GEMINI_API_KEY set")
        raise RuntimeError(_NO_KEY)
    if has_nvidia:
        try:
            return _nvidia_call(prompt, temperature, parse, deadline)
        except RuntimeError:
            if not has_gemini:
                raise
            logger.warning("NVIDIA unavailable; falling back to Gemini")
    # Someone may be waiting: never wait on Gemini longer than what is left of the caller's budget.
    left = None if deadline is None else max(5.0, deadline - time.monotonic())
    timeout = min(GEMINI_TIMEOUT_S, left) if left else None
    for attempt in (1, 2):
        text = _gemini_text(prompt, temperature, json_mode=json_mode, timeout=timeout)
        try:
            return parse(text)
        except ValueError as exc:  # JSON that does not parse: ask once more, it is rarely the same mistake twice
            if attempt == 2:
                raise RuntimeError(f"Gemini answered something that could not be read ({exc})") from exc
            logger.warning("Gemini answer was not valid JSON (%s); asking again", exc)
    raise RuntimeError("unreachable")  # pragma: no cover


def llm_json(prompt: str, *, temperature: float = 0.2, budget_s: float | None = None) -> Any:
    """`budget_s` caps the whole call across NVIDIA's models (someone is waiting on the answer)."""
    return _run(prompt, temperature, _parse_json, None if budget_s is None else time.monotonic() + budget_s, json_mode=True)


def llm_text(prompt: str, *, temperature: float = 0.2) -> str:
    return _run(prompt, temperature, lambda t: _strip_think(t))


def llm_available() -> bool:
    return bool(_key("GEMINI_API_KEY") or (_key("NVIDIA_API_KEY") and not _nvidia_key_rejected))
