"""Discover URLs by searching in a headless browser (not LLM guesses).

Search engine priority:
  1. Bing (bing.com/search)               — primary; answers headless Chromium reliably.
  2. DuckDuckGo HTML (html.duckduckgo.com) — fallback when Bing fails or returns zero results.
     DDG often answers headless browsers with a bot check (no results) or hangs, so after it
     fails once it is skipped for the rest of the browser session.
"""

from __future__ import annotations

import base64
import logging
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from discovery.schemas import SearchHit
from discovery.search import dedupe_hits
from inspector.browser import browser_session

logger = logging.getLogger(__name__)


# Search engine configurations
_DDG_URL  = "https://html.duckduckgo.com/html/"
_BING_URL = "https://www.bing.com/search"

_DDG_SELECTORS  = "a.result__a, a.result-link"
_BING_SELECTORS = "li.b_algo h2 a"

_DDG_TIMEOUT_MS = 10_000
_BING_RESULTS_TIMEOUT_MS = 15_000

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
    if "bing.com" in parsed.netloc:
        raw = parse_qs(parsed.query).get("u", [None])[0]
        if raw and raw.startswith("a1"):
            try:
                # URL-safe base64 ("-" and "_"), padding stripped.
                b64_str = raw[2:]
                b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
                url = base64.urlsafe_b64decode(b64_str).decode("utf-8")
                if url.startswith(("http://", "https://")):
                    return url
            except Exception:
                pass
        # A Bing link we can't resolve (tracking, images, videos) is never a source.
        return None
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return href.split("#")[0]
    return None



# Per-engine page scrapers
def _scrape_ddg(page: Page, query: str, *, max_results: int = 10) -> list[SearchHit]:
    """Attempt a single query on DuckDuckGo HTML. Raises on network failure."""
    hits: list[SearchHit] = []
    page.goto(f"{_DDG_URL}?q={quote(query)}", wait_until="domcontentloaded", timeout=_DDG_TIMEOUT_MS)
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
    """Attempt a single query on Bing. Raises on network failure; no results is an empty list."""
    for attempt in (1, 2):
        try:
            page.goto(f"{_BING_URL}?q={quote(query)}", wait_until="domcontentloaded", timeout=30_000)
            try:
                # Bing can navigate again after DOMContentLoaded, so wait for the results themselves.
                page.wait_for_selector(_BING_SELECTORS, timeout=_BING_RESULTS_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                return []
            return _read_bing_hits(page, query, max_results)
        except PlaywrightError as exc:
            # Both mean another navigation cut in (Bing redirecting); the retry usually lands.
            if attempt == 1 and any(s in str(exc) for s in ("Execution context was destroyed", "net::ERR_ABORTED")):
                continue
            raise
    return []


def _read_bing_hits(page: Page, query: str, max_results: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
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


class _EngineState:
    """Per browser session. DDG is skipped once it fails: a bot check never clears mid-session."""

    def __init__(self) -> None:
        self.ddg_ok = True


def _search_on_page(
    page: Page, query: str, *, max_results: int = 10, state: _EngineState | None = None
) -> list[SearchHit]:
    """
    Run a single query — Bing first, DDG as fallback.

    Falls back to DDG if Bing raises or returns zero results, until DDG itself fails
    or comes back empty (blocked silently); then DDG is off for the session.
    """
    state = state or _EngineState()
    try:
        hits = _scrape_bing(page, query, max_results=max_results)
        if hits:
            return hits
        logger.debug("Bing returned 0 results for %r.", query[:80])
    except Exception as exc:
        logger.warning("Bing failed for %r (%s).", query[:80], exc)

    if not state.ddg_ok:
        return []
    try:
        hits = _scrape_ddg(page, query, max_results=max_results)
    except Exception as exc:
        logger.warning("DDG fallback failed for %r (%s); skipping DDG for this session.", query[:80], exc)
        state.ddg_ok = False
        return []
    if not hits:
        state.ddg_ok = False
    return hits


# Public entry point
def browser_search_queries(queries: list[str], *, max_results_per_query: int = 8) -> list[SearchHit]:
    """Search all queries and return deduplicated hits."""
    if not queries:
        return []
    combined: list[SearchHit] = []
    try:
        with browser_session() as page:
            state = _EngineState()
            for q in queries:
                combined.extend(_search_on_page(page, q, max_results=max_results_per_query, state=state))
    except Exception:
        logger.exception("Browser search session failed entirely.")
    return dedupe_hits(combined)
