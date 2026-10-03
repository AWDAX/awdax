"""
Resolve a search query → candidate URLs (Gemini Google Search grounding, search APIs, fallback).
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from reasoning import ScrapeIntent, gemini_json

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


def _model_name() -> str:
    return os.getenv("GEMINI_SEARCH_MODEL") or os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _api_search(query: str, *, max_results: int = 6) -> list[dict[str, str]]:
    from discovery import _web_search

    return _web_search(query, max_results=max_results)


def _urls_from_grounding(resp: Any) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    try:
        for cand in getattr(resp, "candidates", []) or []:
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = (getattr(web, "uri", None) or "").strip()
                title = (getattr(web, "title", None) or "").strip()
                if uri.startswith("http") and uri not in seen:
                    seen.add(uri)
                    hits.append({"url": uri, "title": title, "snippet": ""})
            supports = getattr(gm, "grounding_supports", None) or []
            for sup in supports:
                for idx in getattr(sup, "grounding_chunk_indices", []) or []:
                    if idx < len(chunks):
                        web = getattr(chunks[idx], "web", None)
                        if web:
                            uri = (getattr(web, "uri", None) or "").strip()
                            if uri.startswith("http") and uri not in seen:
                                seen.add(uri)
                                hits.append({"url": uri, "title": "", "snippet": ""})
    except Exception as e:
        logger.debug("grounding parse: %s", e)
    return hits


def _urls_from_text(text: str, *, query: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in re.findall(r"https://[^\s\)\]\"'<>]+", text or ""):
        url = raw.rstrip(".,;")
        if url not in seen:
            seen.add(url)
            hits.append({"url": url, "title": "", "snippet": query})
    return hits


def _gemini_grounded_search(query: str, intent: ScrapeIntent) -> list[dict[str, str]]:
    if not GEMINI_AVAILABLE:
        return []
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return []

    genai.configure(api_key=api_key)
    model_name = _model_name()
    prompt = f"""You are helping pick web pages to scrape.

Google search query: {query}
User scraping goal: {intent.raw_prompt or intent.topic}

Find real pages (especially comparison/list/category pages with prices or tables) that answer the query.
Prefer aggregators (CarDekho, CarWale, 91Wheels, ZigWheels) or Wikipedia list pages when relevant."""

    tool_variants: list[Any] = [
        [{"google_search": {}}],
        "google_search_retrieval",
        [{"google_search_retrieval": {"dynamic_retrieval_config": {"mode": "MODE_DYNAMIC"}}}],
    ]

    for tools in tool_variants:
        try:
            model = genai.GenerativeModel(model_name, tools=tools)
            resp = model.generate_content(prompt)
            hits = _urls_from_grounding(resp)
            if not hits and resp.text:
                hits = _urls_from_text(resp.text, query=query)
            if hits:
                logger.info("Gemini grounded search returned %d URLs for %r", len(hits), query)
                return hits[:8]
        except Exception as e:
            logger.debug("Gemini tools %s failed: %s", tools, e)
            continue
    return []


def _gemini_propose_url(query: str, intent: ScrapeIntent, *, exclude: list[str] | None = None) -> list[dict[str, str]]:
    exclude = exclude or []
    prompt = f"""Pick ONE best HTTPS URL to scrape for this search query.

Query: {query}
User goal: {intent.raw_prompt or intent.topic}

Return JSON object:
- url (https:// full URL to a list/comparison/category page, not a homepage only)
- title (page title)
- slug (short path description, e.g. /electric-cars)

Use real, well-known sites. Do not invent paths; use typical aggregator category URLs when unsure.

Already used (exclude): {json.dumps(exclude[:15])}"""
    try:
        data = gemini_json(prompt)
    except Exception as e:
        logger.warning("Gemini URL propose failed: %s", e)
        return []
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return []
    url = str(data.get("url") or "").strip()
    if not url.startswith("https://"):
        return []
    return [
        {
            "url": url,
            "title": str(data.get("title") or ""),
            "snippet": str(data.get("slug") or query),
        }
    ]


def search_hits_for_query(
    query: str,
    intent: ScrapeIntent,
    *,
    exclude_urls: set[str] | None = None,
) -> list[dict[str, str]]:
    """
    Order: Serper/Tavily (if keys) → Gemini Google Search grounding → Gemini URL propose.
    """
    exclude_urls = exclude_urls or set()
    backend = (os.getenv("SOURCE_SEARCH_BACKEND") or "auto").lower()

    def _filter(hits: list[dict[str, str]]) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for h in hits:
            url = (h.get("url") or "").strip()
            if url.startswith("https://") and url not in exclude_urls:
                out.append({**h, "url": url})
        return out

    if backend in ("auto", "api", "gemini"):
        api_hits = _filter(_api_search(query, max_results=12))
        if api_hits:
            return api_hits

    if backend in ("auto", "gemini") and os.getenv("SOURCE_SEARCH_GEMINI", "1") != "0":
        grounded = _filter(_gemini_grounded_search(query, intent))
        if grounded:
            return grounded
        proposed = _filter(_gemini_propose_url(query, intent, exclude=list(exclude_urls)))
        if proposed:
            from discovery import probe_https, normalize_https

            verified: list[dict[str, str]] = []
            for h in proposed:
                probe = probe_https(h["url"])
                if probe.get("https_ok"):
                    final = normalize_https(str(probe.get("final_url") or h["url"]))
                    verified.append({**h, "url": final})
                else:
                    logger.info("Proposed URL not reachable: %s", h["url"])
            if verified:
                return verified
            return proposed

    if backend in ("auto", "selenium") and os.getenv("USE_SELENIUM_GOOGLE", "0") == "1":
        try:
            from google_search import create_google_driver, google_search

            driver = create_google_driver()
            try:
                return _filter(google_search(driver, query, max_results=6))
            finally:
                driver.quit()
        except Exception as e:
            logger.warning("Selenium Google search failed: %s", e)

    return []
