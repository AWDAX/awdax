"""
Resolve a search query → candidate URLs (Gemini Google Search grounding, search APIs, fallback).
"""

from __future__ import annotations

import json
import logging
import os
import re

from llm_client import _parse_json
from reasoning import ScrapeIntent, gemini_json

logger = logging.getLogger(__name__)


def _api_search(query: str, *, max_results: int = 6) -> list[dict[str, str]]:
    from discovery import _web_search

    return _web_search(query, max_results=max_results)


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
    """Gemini with Google Search (REST, gemini_search): the pages a real search finds for `query`. The pages Google's
    results cited come first (they exist); then the pages the model named, which it sometimes guesses (a guessed path is
    caught by the plain request that follows and recorded as a failed link)."""
    from gemini_search import cited_pages, grounded_answer, is_redirect_link, search_available

    if not search_available():
        return []
    prompt = f"""Search Google for the query below and find real web pages that LIST the records the user wants
(tables, lists, search/index pages, directories, datasets). Prefer the primary publisher of the records, then public
databases and reputable aggregators. Never invent a URL: only pages you saw in the results.

Google search query: {query}
User's goal: {intent.raw_prompt or intent.topic}

Return JSON only: {{"pages": [{{"url": "https://...", "title": "...", "why": "..."}}]}} with up to 8 pages, best first."""
    try:
        answer = grounded_answer(prompt, timeout=90)
    except RuntimeError as e:
        logger.warning("Gemini grounded search failed for %r: %s", query, e)
        return []
    named: list[dict[str, str]] = []
    try:
        data = _parse_json(answer.text)
        pages = data.get("pages") if isinstance(data, dict) else data
        for p in pages if isinstance(pages, list) else []:
            if isinstance(p, dict) and str(p.get("url") or "").startswith("https://"):
                named.append({"url": str(p["url"]).strip(), "title": str(p.get("title") or ""), "snippet": str(p.get("why") or query)})
    except ValueError:
        named = _urls_from_text(answer.text, query=query)
    cited = [{**c, "snippet": query} for c in cited_pages(answer)]
    seen: set[str] = set()
    unique = [
        h for h in cited + named
        if not is_redirect_link(h["url"]) and not (h["url"].rstrip("/") in seen or seen.add(h["url"].rstrip("/")))
    ]
    logger.info("Gemini grounded search returned %d URLs for %r", len(unique), query)
    return unique[:8]


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
