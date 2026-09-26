"""Discover URLs by searching in a headless browser (not LLM guesses)."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Page

from discovery.schemas import SearchHit
from discovery.search import dedupe_hits
from inspector.browser import browser_session

logger = logging.getLogger(__name__)

_DDG_HTML = "https://html.duckduckgo.com/html/"


def search_query_variants(user_goal: str, round_idx: int) -> list[str]:
    goal = user_goal.strip()
    base = [
        goal,
        f"{goal} price list India",
        f"{goal} site:cardekho.com",
        f"{goal} site:carwale.com",
        f"{goal} site:zigwheels.com",
        f"electric cars India ex-showroom price",
        f"all EV models India price list",
    ]
    seen: set[str] = set()
    ordered: list[str] = []
    for q in base:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            ordered.append(q)
    if round_idx <= 0:
        return ordered[:3]
    start = min(round_idx * 2, len(ordered) - 1)
    return ordered[start : start + 2] or ordered[-2:]


def _unwrap_result_url(href: str) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and "uddg=" in parsed.query:
        raw = parse_qs(parsed.query).get("uddg", [None])[0]
        if raw:
            return unquote(raw)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return href.split("#")[0]
    return None


def _search_on_page(page: Page, query: str, *, max_results: int = 10) -> list[SearchHit]:
    from urllib.parse import quote

    hits: list[SearchHit] = []
    try:
        page.goto(f"{_DDG_HTML}?q={quote(query)}", wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(600)
        anchors = page.query_selector_all("a.result__a, a.result-link")
        for a in anchors:
            href = _unwrap_result_url(a.get_attribute("href") or "")
            if not href:
                continue
            title = (a.inner_text() or href).strip()
            title = re.sub(r"\s+", " ", title)[:500]
            hits.append(
                SearchHit(
                    url=href,
                    title=title,
                    snippet=f"Headless search: {query[:120]}",
                    from_dork=query,
                )
            )
            if len(hits) >= max_results:
                break
    except Exception as exc:
        logger.warning("Browser search failed for %r: %s", query[:80], exc)
    return hits


def browser_search_queries(queries: list[str], *, max_results_per_query: int = 8) -> list[SearchHit]:
    if not queries:
        return []
    combined: list[SearchHit] = []
    try:
        with browser_session() as page:
            for q in queries:
                combined.extend(_search_on_page(page, q, max_results=max_results_per_query))
    except Exception:
        logger.exception("Browser search session failed")
    return dedupe_hits(combined)
