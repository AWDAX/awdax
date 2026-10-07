"""
Research first, scrape second: before any page is opened, the model searches the web the way a person would and names the
best websites for the request, ranked. Discovery then tries them in that order (rank 1 first), before its own searches.

Nothing here knows about any topic or site: the ranking comes from live Google results for the user's own words.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import urlsplit

from llm_client import _parse_json
from reasoning import ScrapeIntent

logger = logging.getLogger(__name__)

TOP_N = 5

SYSTEM = """You are a senior research analyst. A user wants a DATASET (rows of real records) about the request below.
Your job is to do what an expert does before collecting data: search the web for the latest information, see which websites
actually publish these records, and pick the best ones to collect from.

How to work:
1. Search Google with several phrasings of the request (plain words, the official names of the bodies involved, the names of
   the record types). Look at what the results really contain; do not rely on memory.
2. Prefer, in this order: the official or primary publisher of the records; established public databases, archives and
   open-data portals; reputable aggregators that list the records in tables or lists; downloadable datasets (CSV/JSON/XLSX).
3. For each website give the DEEP LINK to the page that lists the records (a search, index, listing, table or dataset page),
   not a homepage or an article about the topic, unless the homepage itself is that listing.
4. Never invent a URL. Every URL must be one you saw in the search results or on a page you found.
5. Stay neutral: rank only by how directly and completely each site holds the records the user asked for (coverage of the
   requested period, place and fields, accuracy, freshness). No site is preferred for any other reason.
6. Respect the request's constraints (dates, place, record type) when judging coverage."""

SCHEMA = """Return JSON only, in exactly this shape, best first:
{
  "understanding": "<one sentence: what records the user wants, for which period/place>",
  "websites": [
    {
      "rank": 1,
      "url": "https://...deep link to the listing/search/dataset page...",
      "site_name": "<publisher or site>",
      "what_it_has": "<which records, which fields, which years/places>",
      "format": "<html table | html list | search results | pdf | csv | json | xlsx | api | other>",
      "why": "<why this rank: authority, coverage, freshness>"
    }
  ]
}
Give exactly {n} websites (fewer only if fewer exist), ranked 1..{n}, each on a different page."""


def _clean(item: Any, rank: int) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or "").strip().rstrip(".,;)")
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or "." not in parts.hostname:
        return None
    return {
        "rank": rank,
        "url": url,
        "domain": parts.hostname.lower().removeprefix("www."),
        "site_name": str(item.get("site_name") or parts.hostname)[:120],
        "what_it_has": str(item.get("what_it_has") or "")[:400],
        "format": str(item.get("format") or "")[:40],
        "why": str(item.get("why") or "")[:300],
    }


def _websites(data: Any, n: int) -> list[dict[str, str]]:
    items = data.get("websites") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    ranked = sorted((x for x in items if isinstance(x, dict)), key=lambda x: _rank_of(x))
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in ranked:
        site = _clean(item, len(out) + 1)
        if site and site["url"].rstrip("/") not in seen:
            seen.add(site["url"].rstrip("/"))
            out.append(site)
        if len(out) >= n:
            break
    return out


def _same_site(url: str, domain: str) -> bool:
    host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    return bool(host) and (host == domain or host.endswith("." + domain) or domain.endswith("." + host))


def _rank_of(item: dict[str, Any]) -> float:
    try:
        return float(item.get("rank"))
    except (TypeError, ValueError):
        return 1e9


def top_n() -> int:
    try:
        return max(1, min(int(os.getenv("RESEARCH_TOP_SITES", str(TOP_N))), 10))
    except ValueError:
        return TOP_N


def build_prompt(intent: ScrapeIntent, n: int) -> str:
    details = {k: v for k, v in {
        "topic": intent.topic,
        "place": intent.geography,
        "record types": intent.entity_types,
        "fields wanted": intent.output_fields,
        "constraints": intent.constraints,
        "freshness": intent.freshness,
        "sites the user named": intent.named_sites,
    }.items() if v}
    return f"""{SYSTEM}

User request: {intent.raw_prompt or intent.topic}
What we understood so far: {json.dumps(details, ensure_ascii=False, default=str)}

{SCHEMA.replace("{n}", str(n))}"""


def research_top_sites(intent: ScrapeIntent, *, n: int | None = None) -> dict[str, Any]:
    """{"understanding", "websites": [...ranked...], "searched": [queries the model ran], "grounded_domains": [...]}.
    Empty websites when search is unavailable or failed: discovery then runs as before, on its own searches."""
    from gemini_search import cited_pages, grounded_answer, is_redirect_link, search_available

    n = n or top_n()
    empty: dict[str, Any] = {"understanding": "", "websites": [], "searched": [], "grounded_domains": []}
    if os.getenv("RESEARCH_FIRST", "1") == "0" or not search_available():
        return empty
    try:
        answer = grounded_answer(build_prompt(intent, n))
    except RuntimeError as exc:
        logger.warning("Web research failed: %s", exc)
        return {**empty, "error": str(exc)[:200]}
    try:
        data = _parse_json(answer.text)
    except ValueError:
        # Not JSON: keep any real links the answer mentions, in the order given.
        data = {"websites": [{"url": u} for u in re.findall(r"https://[^\s\)\]\"'<>]+", answer.text)]}
    domains = answer.source_domains()
    websites = [s for s in _websites(data, n) if not is_redirect_link(s["url"])]
    cited = [c["url"] for c in cited_pages(answer, limit=10)]
    for site in websites:
        # Pages on the same site that Google's results cited: tried instead when the model's own deep link turns out not to
        # exist (models get the path wrong more often than the site).
        site["alt_urls"] = [u for u in cited if _same_site(u, site["domain"]) and u.rstrip("/") != site["url"].rstrip("/")][:3]
        # Seen in the Google results the model searched, or only from its own knowledge. Both are tried; the plain request
        # that follows is what proves a page exists.
        site["grounded"] = "yes" if any(site["domain"] == d or site["domain"].endswith("." + d) or d.endswith("." + site["domain"]) for d in domains) else "no"
    return {
        "understanding": str(data.get("understanding") or "")[:300] if isinstance(data, dict) else "",
        "websites": websites,
        "searched": answer.queries[:12],
        "grounded_domains": sorted(domains)[:30],
    }
