"""
Gemini with Google Search, over the REST API.

The google-generativeai SDK this project uses cannot attach the `google_search` tool to Gemini 3 models (it raises
"Unknown field for FunctionDeclaration: google_search", and the older `google_search_retrieval` tool answers 400). Every
grounded search therefore came back empty and discovery ran on guesses. The REST endpoint takes the tool as plain JSON, so
no new package is needed.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = 120.0
# Google's grounding links are redirects through this host; resolving one costs a request, so only a few are resolved.
_REDIRECT_HOST = "vertexaisearch.cloud.google.com"


@dataclass
class GroundedAnswer:
    text: str = ""
    queries: list[str] = field(default_factory=list)  # what the model searched Google for
    sources: list[dict[str, str]] = field(default_factory=list)  # {"title": domain or page title, "url": redirect or real url}

    def source_domains(self) -> set[str]:
        out: set[str] = set()
        for s in self.sources:
            title = (s.get("title") or "").strip().lower()
            host = (urlsplit(s.get("url") or "").hostname or "").lower()
            for value in (title, host):
                if value and "." in value and " " not in value and _REDIRECT_HOST not in value:
                    out.add(value.removeprefix("www."))
        return out


def _key() -> str:
    v = (os.getenv("GEMINI_API_KEY") or "").strip()
    return "" if v.startswith("your_") else v


def search_available() -> bool:
    return bool(_key()) and os.getenv("SOURCE_SEARCH_GEMINI", "1") != "0"


def _models() -> list[str]:
    from llm_client import DEFAULT_GEMINI_MODEL, FALLBACK_GEMINI_MODEL

    chosen = (os.getenv("GEMINI_SEARCH_MODEL") or os.getenv("GEMINI_MODEL") or "").strip() or DEFAULT_GEMINI_MODEL
    return [chosen] if chosen == FALLBACK_GEMINI_MODEL else [chosen, FALLBACK_GEMINI_MODEL]


def _parse(data: dict[str, Any]) -> GroundedAnswer:
    cand = (data.get("candidates") or [{}])[0] or {}
    text = "".join(str(p.get("text") or "") for p in (cand.get("content") or {}).get("parts") or [] if not p.get("thought"))
    meta = cand.get("groundingMetadata") or {}
    sources = []
    for chunk in meta.get("groundingChunks") or []:
        web = chunk.get("web") or {}
        if web.get("uri"):
            sources.append({"title": str(web.get("title") or ""), "url": str(web["uri"])})
    return GroundedAnswer(text=text.strip(), queries=[str(q) for q in meta.get("webSearchQueries") or []], sources=sources)


def grounded_answer(prompt: str, *, timeout: float = TIMEOUT_S) -> GroundedAnswer:
    """One answer from Gemini with Google Search switched on. Raises RuntimeError when no model answered."""
    key = _key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "tools": [{"google_search": {}}]}
    last = "no model answered"
    for model in _models():
        for attempt in (1, 2):
            try:
                res = requests.post(API.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=timeout)
            except requests.RequestException as exc:
                last = f"{type(exc).__name__}: {exc}"
                break
            if res.status_code == 200:
                return _parse(res.json())
            last = f"{model}: HTTP {res.status_code} {res.text[:200]}"
            if res.status_code in (429, 500, 503) and attempt == 1:
                time.sleep(2)
                continue
            break
        if "HTTP 404" not in last:  # only a model that is gone moves on to the fallback model
            break
        logger.warning("Gemini search model gone (%s); trying the fallback", last)
    raise RuntimeError(f"Gemini search failed ({last})")


def is_redirect_link(url: str) -> bool:
    return _REDIRECT_HOST in (urlsplit(url or "").hostname or "")


def cited_pages(answer: GroundedAnswer, *, limit: int = 8) -> list[dict[str, str]]:
    """The pages Google's results actually cited for this answer, as real addresses (redirects resolved at once, in order).
    These exist: unlike a URL the model writes itself, they were in the search results."""
    from concurrent.futures import ThreadPoolExecutor

    links = []
    for s in answer.sources:
        if s.get("url") and s["url"] not in [x["url"] for x in links]:
            links.append(s)
    links = links[:limit]
    if not links:
        return []
    with ThreadPoolExecutor(max_workers=min(len(links), 8)) as pool:
        resolved = list(pool.map(lambda s: resolve_redirect(s["url"]), links))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for s, url in zip(links, resolved):
        if url.startswith("https://") and not is_redirect_link(url) and url not in seen:
            seen.add(url)
            out.append({"url": url, "title": s.get("title") or ""})
    return out


def resolve_redirect(url: str, *, timeout: float = 8.0) -> str:
    """The real address behind one of Google's grounding redirect links (one plain request, no body read). The link
    itself when it is not a redirect or cannot be resolved."""
    if _REDIRECT_HOST not in (urlsplit(url).hostname or ""):
        return url
    try:
        res = requests.head(url, allow_redirects=False, timeout=timeout)
        target = res.headers.get("location") or ""
        return target if target.startswith("http") else url
    except requests.RequestException:
        return url
