"""
Discover candidate sources for a ScrapeIntent (hybrid search + Gemini legit filter).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

from url_guard import UnsafeURL, UnresolvableHost, safe_get

from reasoning import ScrapeIntent, gemini_json

logger = __import__("logging").getLogger(__name__)

GOV_TLD_BONUS = (".gov.in", ".nic.in", ".gov.", ".edu.")
_PDF_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

try:
    import certifi

    _VERIFY = certifi.where()
except ImportError:
    _VERIFY = True


@dataclass
class SourceCandidate:
    url: str
    title: str = ""
    snippet: str = ""
    relevance_score: float = 0.0
    legit_score: float = 0.0
    legit_reason: str = ""
    verified_search: bool = False
    domain: str = ""
    https_ok: bool = False
    final_url: str = ""
    table_headers_preview: list[str] | None = None
    table_count: int = 0
    source_category: str = ""
    http_status: int = 0
    search_query: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceCandidate:
        url = normalize_https(str(data.get("url") or data.get("final_url") or "").strip())
        domain = urlparse(url).netloc.lower()
        th = data.get("table_headers_preview")
        return cls(
            url=url,
            title=str(data.get("title") or ""),
            snippet=str(data.get("snippet") or ""),
            relevance_score=float(data.get("relevance_score") or 0),
            legit_score=float(data.get("legit_score") or 0),
            legit_reason=str(data.get("legit_reason") or ""),
            verified_search=bool(data.get("verified_search")),
            domain=str(data.get("domain") or domain),
            https_ok=bool(data.get("https_ok")),
            final_url=str(data.get("final_url") or url),
            table_headers_preview=list(th) if th else None,
            table_count=int(data.get("table_count") or 0),
            source_category=str(data.get("source_category") or ""),
            http_status=int(data.get("http_status") or 0),
            search_query=str(data.get("search_query") or ""),
        )


def normalize_https(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    elif not url.startswith("https://"):
        url = "https://" + url.lstrip("/")
    try:
        p = urlparse(url)
        netloc = (p.netloc or "").lower()
        url = urlunparse(("https", netloc, p.path or "", p.params, p.query, p.fragment))
    except Exception:
        pass
    return url


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": _PDF_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }


def fetch_html(url: str, *, max_chars: int = 600_000) -> dict[str, Any]:
    """HTTPS GET with browser-like headers; keep body even on 403 for scrape attempts."""
    url = normalize_https(url)
    out: dict[str, Any] = {
        "https_ok": False,
        "final_url": url,
        "title": "",
        "table_headers_preview": [],
        "table_count": 0,
        "html": "",
        "http_status": 0,
        "error": None,
        "blocked": False,
    }
    if not url.startswith("https://"):
        out["error"] = "invalid url"
        return out
    last_err: Exception | None = None
    for verify in (_VERIFY, False):
        try:
            # The body is read only up to max_bytes (4 bytes per char covers any UTF-8 text), then cut to max_chars as before.
            r = safe_get(
                url,
                timeout=25,
                verify=verify,
                headers=_request_headers(),
                max_bytes=max_chars * 4,
            )
            html = (r.text or "")[:max_chars]
            out["final_url"] = normalize_https(r.url)
            out["http_status"] = int(r.status_code)
            out["html"] = html
            # Reachable if we got meaningful HTML (many OEM sites return 403 to bots but 200 with body elsewhere)
            out["https_ok"] = len(html) > 400 and r.status_code < 500
            if not out["https_ok"] and r.status_code in (403, 401) and len(html) > 800:
                out["https_ok"] = True
            tm = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
            if tm:
                out["title"] = re.sub(r"\s+", " ", tm.group(1)).strip()[:200]
            out["table_count"] = len(re.findall(r"<table\b", html, re.I))
            headers = re.findall(r"<th[^>]*>([^<]+)</th>", html, re.I)
            out["table_headers_preview"] = [re.sub(r"\s+", " ", h).strip() for h in headers if h.strip()][:25]
            from dataset_files import find_dataset_links

            out["dataset_links"] = find_dataset_links(html, out["final_url"])
            if not out["https_ok"]:
                out["error"] = f"HTTP {r.status_code}, body={len(html)} bytes"
            return out
        except UnsafeURL as e:
            # Not a fetch failure to retry (the verify=False pass would be refused the same way): a blocked source.
            out["error"] = str(e)
            out["blocked"] = not isinstance(e, UnresolvableHost)
            return out
        except Exception as e:
            last_err = e
            continue
    out["error"] = str(last_err) if last_err else "fetch failed"
    return out


def probe_https(url: str) -> dict[str, Any]:
    """Lightweight probe (no full html in return for discovery lists)."""
    full = fetch_html(url, max_chars=120_000)
    try:
        from listing_extract import visible_text_length

        visible = visible_text_length(full.get("html") or "")
    except Exception:  # noqa: BLE001 - only used to tell whether JavaScript adds content
        visible = -1
    return {
        "visible_chars": visible,
        "https_ok": full.get("https_ok"),
        "final_url": full.get("final_url"),
        "title": full.get("title"),
        "table_headers_preview": full.get("table_headers_preview"),
        "table_count": full.get("table_count"),
        "http_status": full.get("http_status"),
        "error": full.get("error"),
        "blocked": bool(full.get("blocked")),
        "dataset_links": full.get("dataset_links") or [],
    }


def _intent_is_regulatory(intent: ScrapeIntent) -> bool:
    blob = " ".join(
        [intent.topic, intent.geography, " ".join(intent.constraints), " ".join(intent.entity_types)]
    ).lower()
    return any(
        k in blob
        for k in (
            "regulatory",
            "gazette",
            "compliance",
            "rbi",
            "sebi",
            "notification",
            "government",
            "ministry",
            "legal",
        )
    )


def _search_queries(intent: ScrapeIntent) -> list[str]:
    geo = intent.geography or "India"
    if _intent_is_regulatory(intent):
        parts = [intent.topic, geo]
        return list(
            dict.fromkeys(
                [
                    " ".join(parts) + " official site",
                    " ".join(parts) + " government data",
                    intent.topic + " site:gov.in",
                ]
            )
        )[:4]
    topic = intent.topic
    from listing_sources import intent_wants_ev_catalog

    if intent_wants_ev_catalog(intent):
        return list(
            dict.fromkeys(
                [
                    f"{topic} {geo} price list comparison cardekho carwale",
                    f"{topic} {geo} wikipedia list",
                    f"{topic} {geo} news article prices",
                    f"{topic} {geo} specifications table",
                    f"{topic} site:cardekho.com OR site:carwale.com OR site:91wheels.com",
                    topic,
                ]
            )
        )[:6]
    return list(
        dict.fromkeys(
            [
                f"{topic} {geo} list comparison",
                f"{topic} {geo} wikipedia list",
                f"{topic} {geo} directory",
                f"{topic} {geo} data table",
                topic,
            ]
        )
    )[:6]


def _tavily_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        return []
    try:
        r = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "max_results": max_results},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("results") or []
        out = []
        for item in results:
            out.append(
                {
                    "url": item.get("url") or "",
                    "title": item.get("title") or "",
                    "snippet": item.get("content") or item.get("snippet") or "",
                }
            )
        return out
    except Exception as e:
        logger.warning("Tavily search failed: %s", e)
        return []


def _serper_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    key = os.getenv("SERPER_API_KEY")
    if not key:
        return []
    try:
        r = requests.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": max_results},
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("organic") or []
        out = []
        for item in results:
            out.append(
                {
                    "url": item.get("link") or "",
                    "title": item.get("title") or "",
                    "snippet": item.get("snippet") or "",
                }
            )
        return out
    except Exception as e:
        logger.warning("Serper search failed: %s", e)
        return []


def _web_search(query: str, max_results: int = 8) -> list[dict[str, str]]:
    if os.getenv("TAVILY_API_KEY"):
        return _tavily_search(query, max_results)
    if os.getenv("SERPER_API_KEY"):
        return _serper_search(query, max_results)
    return []


def _gemini_propose_sources(
    intent: ScrapeIntent,
    count: int = 12,
    *,
    exclude_urls: list[str] | None = None,
    diversity: bool = False,
) -> list[dict[str, str]]:
    reg = _intent_is_regulatory(intent)
    exclude_urls = exclude_urls or []
    if reg:
        diversity_block = "Prefer official government/regulator primary sources."
    elif diversity:
        from table_merge import intent_avoid_oem_sites

        if intent_avoid_oem_sites(intent):
            diversity_block = """You MUST NOT include manufacturer/OEM brand sites (Tata, Hyundai, MG, Mahindra, BYD official sites).
Use ONLY comparison/aggregator sites (CarDekho, CarWale, 91Wheels, ZigWheels), Wikipedia lists, news/reviews with price tables.
Assign source_category: aggregator|wiki|news|government|other — never manufacturer."""
        else:
            diversity_block = """You MUST include a MIX of source types (assign source_category on each):
- at most 3 manufacturer/OEM official sites
- at least 2 comparison/aggregator sites (e.g. CarDekho, CarWale, 91Wheels, ZigWheels)
- at least 1 Wikipedia or educational list page
- at least 1 news or review site with price data
- at least 1 government/policy page if relevant
Do NOT return only car brand homepages."""
    else:
        diversity_block = "Mix OEM, aggregators, Wikipedia, and news — not only brand marketing pages."

    prompt = f"""Propose exactly {count} distinct HTTPS URLs for scraping this intent.
Return JSON array of objects:
- url (https://...)
- title
- snippet
- source_category (manufacturer|aggregator|wiki|news|government|other)

{ diversity_block }

Exclude these URLs (already have): {json.dumps(exclude_urls[:30])}

Intent:
{json.dumps(intent.to_dict(), indent=2)}"""
    data = gemini_json(prompt)
    if isinstance(data, dict) and "sources" in data:
        data = data["sources"]
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("url")]


def _domain_key(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _rule_legit_boost(url: str) -> float:
    u = url.lower()
    bonus = 0.0
    for tld in GOV_TLD_BONUS:
        if tld in u:
            bonus += 0.15
    if "egazette.gov.in" in u:
        bonus += 0.2
    if re.search(r"(blogspot|wordpress\.com|medium\.com)", u):
        bonus -= 0.3
    return bonus


def _rank_with_gemini(intent: ScrapeIntent, candidates: list[dict[str, Any]]) -> list[SourceCandidate]:
    if not candidates:
        return []
    prompt = f"""Score each candidate URL for scraping this intent (public HTML tables/lists).
Return JSON array with objects: url, relevance_score (0-1), legit_score (0-1), legit_reason (short).

Intent:
{json.dumps(intent.to_dict(), indent=2)}

Candidates (https_ok and table hints included):
{json.dumps(candidates[:25], indent=2)}"""
    data = gemini_json(prompt)
    if not isinstance(data, list):
        return []

    by_url = {c["url"]: c for c in candidates if c.get("url")}
    ranked: list[SourceCandidate] = []
    min_legit = 0.25 if not _intent_is_regulatory(intent) else 0.35
    for item in data:
        if not isinstance(item, dict):
            continue
        url = normalize_https(str(item.get("url") or "").strip())
        if not url or url not in by_url:
            continue
        base = by_url[url]
        legit = float(item.get("legit_score") or 0) + _rule_legit_boost(url)
        legit = max(0.0, min(1.0, legit))
        rel = float(item.get("relevance_score") or 0)
        if legit < min_legit:
            continue
        ranked.append(
            SourceCandidate(
                url=url,
                title=str(base.get("title") or ""),
                snippet=str(base.get("snippet") or ""),
                relevance_score=rel,
                legit_score=legit,
                legit_reason=str(item.get("legit_reason") or ""),
                verified_search=bool(base.get("verified_search")),
                domain=_domain_key(url),
                https_ok=bool(base.get("https_ok")),
                final_url=str(base.get("final_url") or url),
                table_headers_preview=base.get("table_headers_preview") or [],
                table_count=int(base.get("table_count") or 0),
                source_category=str(base.get("source_category") or item.get("source_category") or ""),
                http_status=int(base.get("http_status") or 0),
            )
        )
    ranked.sort(
        key=lambda s: (
            s.https_ok,
            s.table_count > 0,
            (s.legit_score + s.relevance_score) / 2,
        ),
        reverse=True,
    )
    return ranked


def _candidate_from_meta(c: dict[str, Any], *, default_legit: float = 0.5) -> SourceCandidate:
    url = c.get("url") or c.get("final_url") or ""
    return SourceCandidate(
        url=url,
        title=str(c.get("title") or ""),
        snippet=str(c.get("snippet") or ""),
        relevance_score=float(c.get("relevance_score") or 0.45),
        legit_score=float(c.get("legit_score") or default_legit),
        legit_reason=str(c.get("legit_reason") or "discovery pool"),
        verified_search=bool(c.get("verified_search")),
        domain=_domain_key(url),
        https_ok=bool(c.get("https_ok")),
        final_url=str(c.get("final_url") or url),
        table_headers_preview=c.get("table_headers_preview") or [],
        table_count=int(c.get("table_count") or 0),
        source_category=str(c.get("source_category") or "other"),
        http_status=int(c.get("http_status") or 0),
    )


def _build_initial_merged(intent: ScrapeIntent) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for q in _search_queries(intent):
        for hit in _web_search(q, max_results=10):
            url = normalize_https((hit.get("url") or "").strip())
            if not url.startswith("https://"):
                continue
            merged.setdefault(url, {**hit, "url": url, "verified_search": True})

    for diversity_pass in (False, True):
        for hit in _gemini_propose_sources(
            intent,
            count=15,
            exclude_urls=list(merged.keys()),
            diversity=diversity_pass or not _intent_is_regulatory(intent),
        ):
            url = normalize_https((hit.get("url") or "").strip())
            if url.startswith("https://"):
                merged.setdefault(
                    url,
                    {
                        **hit,
                        "url": url,
                        "verified_search": False,
                        "source_category": hit.get("source_category") or "other",
                    },
                )
    return merged


def _probe_merged_pool(merged: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    probed: list[dict[str, Any]] = []
    for url, meta in merged.items():
        probe = probe_https(url)
        entry = {
            "url": probe.get("final_url") or url,
            **meta,
            "https_ok": probe.get("https_ok"),
            "final_url": probe.get("final_url") or url,
            "table_headers_preview": probe.get("table_headers_preview") or [],
            "table_count": probe.get("table_count") or 0,
            "http_status": probe.get("http_status") or 0,
        }
        if probe.get("title") and not entry.get("title"):
            entry["title"] = probe["title"]
        probed.append(entry)

    probed.sort(
        key=lambda c: (c.get("https_ok"), c.get("table_count", 0) > 0, c.get("source_category") != "manufacturer"),
        reverse=True,
    )

    domain_counts: dict[str, int] = {}
    deduped: list[dict[str, Any]] = []
    for c in probed:
        dk = _domain_key(c["url"])
        domain_counts[dk] = domain_counts.get(dk, 0) + 1
        if domain_counts[dk] > 3:
            continue
        deduped.append(c)
    return deduped


def _rank_and_fill_candidates(
    intent: ScrapeIntent,
    deduped: list[dict[str, Any]],
    *,
    seen: set[str],
    max_n: int,
) -> list[SourceCandidate]:
    ranked = _rank_with_gemini(intent, [c for c in deduped if c["url"] not in seen])
    ranked_urls = {s.url for s in ranked}

    def _fill_from_pool(*, require_https: bool) -> None:
        for c in deduped:
            if len(ranked) >= max_n:
                return
            url = c["url"]
            if url in seen or url in ranked_urls:
                continue
            if require_https and not c.get("https_ok"):
                continue
            ranked.append(_candidate_from_meta(c))
            ranked_urls.add(url)

    _fill_from_pool(require_https=True)
    _fill_from_pool(require_https=False)
    ranked.sort(
        key=lambda s: (s.https_ok, s.table_count > 0, s.legit_score + s.relevance_score),
        reverse=True,
    )
    return ranked[:max_n]


def _gemini_probe_batch(
    intent: ScrapeIntent,
    *,
    exclude_urls: set[str],
    count: int = 12,
) -> list[SourceCandidate]:
    extra = _gemini_propose_sources(intent, count=count, exclude_urls=list(exclude_urls), diversity=True)
    if not extra:
        return []
    out: list[SourceCandidate] = []
    for hit in extra:
        url = normalize_https((hit.get("url") or "").strip())
        if not url.startswith("https://") or url in exclude_urls:
            continue
        probe = probe_https(url)
        c = {
            **hit,
            "url": probe.get("final_url") or url,
            "final_url": probe.get("final_url") or url,
            "https_ok": probe.get("https_ok"),
            "table_headers_preview": probe.get("table_headers_preview") or [],
            "table_count": probe.get("table_count") or 0,
            "http_status": probe.get("http_status") or 0,
            "verified_search": False,
        }
        out.append(_candidate_from_meta(c))
    return out


class DiscoveryCandidateFeed:
    """Yield discovery candidates one at a time; refills from Gemini when the queue is empty."""

    def __init__(self, intent: ScrapeIntent):
        self.intent = intent
        self.handled: set[str] = set()
        self._queue: list[SourceCandidate] = []
        self._deduped = _probe_merged_pool(_build_initial_merged(intent))
        self._gemini_rounds = 0
        self._max_gemini_rounds = int(os.getenv("DISCOVERY_GEMINI_ROUNDS", "5"))

    def _refill_queue(self, batch: int = 20) -> bool:
        if self._queue:
            return True
        ranked = _rank_and_fill_candidates(
            self.intent,
            self._deduped,
            seen=self.handled | {c.url for c in self._queue},
            max_n=batch,
        )
        for s in ranked:
            if s.url not in self.handled:
                self._queue.append(s)
        if self._queue:
            return True
        if self._gemini_rounds >= self._max_gemini_rounds:
            return False
        self._gemini_rounds += 1
        for s in _gemini_probe_batch(
            self.intent,
            exclude_urls=self.handled,
            count=12,
        ):
            if s.url not in self.handled:
                self._queue.append(s)
        return bool(self._queue)

    def next_candidate(self) -> SourceCandidate | None:
        if not self._queue and not self._refill_queue():
            return None
        while self._queue:
            c = self._queue.pop(0)
            if c.url in self.handled:
                continue
            self.handled.add(c.url)
            return c
        if self._refill_queue():
            return self.next_candidate()
        return None


def candidate_from_serp_hit(
    hit: dict[str, str],
    *,
    search_query: str,
    source_type_hint: str = "",
    job_id: str = "",
    stage: str = "search",
) -> SourceCandidate:
    url = normalize_https(hit.get("url") or "")
    probe = probe_https(url)  # the plain request every link gets first
    if job_id:
        import url_access

        url_access.record_probe(job_id, url, probe, stage=stage)
    final = normalize_https(str(probe.get("final_url") or url))
    cat = (source_type_hint or "other").lower()
    return SourceCandidate(
        url=final,
        title=str(hit.get("title") or probe.get("title") or ""),
        snippet=str(hit.get("snippet") or search_query),
        relevance_score=0.75,
        legit_score=0.72,
        legit_reason=f"Google organic result for: {search_query}",
        verified_search=True,
        domain=_domain_key(final),
        https_ok=bool(probe.get("https_ok")),
        final_url=final,
        table_headers_preview=probe.get("table_headers_preview") or [],
        table_count=int(probe.get("table_count") or 0),
        source_category=cat,
        http_status=int(probe.get("http_status") or 0),
        search_query=search_query,
    )
