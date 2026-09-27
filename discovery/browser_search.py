"""Discover URLs by searching in a headless browser (not LLM guesses).

Search engine priority:
  1. DuckDuckGo HTML (html.duckduckgo.com) — privacy-friendly, no JS required.
  2. Bing (bing.com/search)               — fallback when DDG is blocked or returns zero results.
"""

from __future__ import annotations

import base64
import logging
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from playwright.sync_api import Page

from discovery.schemas import SearchHit
from discovery.search import dedupe_hits
from inspector.browser import browser_session

logger = logging.getLogger(__name__)


# Search engine configurations
_DDG_URL  = "https://html.duckduckgo.com/html/"
_BING_URL = "https://www.bing.com/search"

_DDG_SELECTORS  = "a.result__a, a.result-link"
_BING_SELECTORS = "li.b_algo h2 a"

# Query variant builder
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


# URL unwrappers — each engine wraps real links differently
def _unwrap_ddg_url(href: str) -> str | None:
    """Resolve DuckDuckGo redirect links (uddg= param) to the real URL."""
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


def _unwrap_bing_url(href: str) -> str | None:
    """Resolve Bing tracking links (u= base64 param) to the real URL."""
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "bing.com" in parsed.netloc and "u=" in parsed.query:
        raw = parse_qs(parsed.query).get("u", [None])[0]
        if raw and raw.startswith("a1"):
            try:
                b64_str = raw[2:]
                # Restore missing base64 padding
                b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
                return base64.b64decode(b64_str).decode("utf-8")
            except Exception:
                pass
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return href.split("#")[0]
    return None



# Per-engine page scrapers
def _scrape_ddg(page: Page, query: str, *, max_results: int = 10) -> list[SearchHit]:
    """Attempt a single query on DuckDuckGo HTML. Raises on network failure."""
    hits: list[SearchHit] = []
    page.goto(f"{_DDG_URL}?q={quote(query)}", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(600)
    for a in page.query_selector_all(_DDG_SELECTORS):
        href = _unwrap_ddg_url(a.get_attribute("href") or "")
        if not href:
            continue
        title = re.sub(r"\s+", " ", (a.inner_text() or href).strip())[:500]
        hits.append(SearchHit(url=href, title=title,
                               snippet=f"DDG search: {query[:120]}", from_dork=query))
        if len(hits) >= max_results:
            break
    return hits


def _scrape_bing(page: Page, query: str, *, max_results: int = 10) -> list[SearchHit]:
    """Attempt a single query on Bing. Raises on network failure."""
    hits: list[SearchHit] = []
    page.goto(f"{_BING_URL}?q={quote(query)}", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(600)
    for a in page.query_selector_all(_BING_SELECTORS):
        href = _unwrap_bing_url(a.get_attribute("href") or "")
        if not href:
            continue
        title = re.sub(r"\s+", " ", (a.inner_text() or href).strip())[:500]
        hits.append(SearchHit(url=href, title=title,
                               snippet=f"Bing fallback: {query[:120]}", from_dork=query))
        if len(hits) >= max_results:
            break
    return hits


def _search_on_page(page: Page, query: str, *, max_results: int = 10) -> list[SearchHit]:
    """
    Run a single query — DDG first, Bing as automatic fallback.

    Falls back to Bing if:
      - DDG raises any network/timeout exception, OR
      - DDG returns zero results (blocked silently).
    """
    # Primary: DuckDuckGo
    try:
        hits = _scrape_ddg(page, query, max_results=max_results)
        if hits:
            return hits
        logger.debug("DDG returned 0 results for %r — trying Bing fallback.", query[:80])
    except Exception as exc:
        logger.warning("DDG failed for %r (%s) — falling back to Bing.", query[:80], exc)

    # Fallback: Bing
    try:
        return _scrape_bing(page, query, max_results=max_results)
    except Exception as exc:
        logger.warning("Bing fallback also failed for %r: %s", query[:80], exc)
        return []


# Public entry point
def browser_search_queries(queries: list[str], *, max_results_per_query: int = 8) -> list[SearchHit]:
    """Search all queries and return deduplicated hits."""
    if not queries:
        return []
    combined: list[SearchHit] = []
    try:
        with browser_session() as page:
            for q in queries:
                combined.extend(_search_on_page(page, q, max_results=max_results_per_query))
    except Exception:
        logger.exception("Browser search session failed entirely.")
    return dedupe_hits(combined)
