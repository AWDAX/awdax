"""URL list helpers (search is done by headless browser, not a search API)."""

from __future__ import annotations

from urllib.parse import urlparse

from discovery.schemas import SearchHit


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return url.strip()
    path = parsed.path.rstrip("/") or ""
    return f"{parsed.scheme}://{parsed.netloc.lower()}{path}"


def hits_from_urls(
    urls: list[str],
    *,
    title: str,
    snippet: str,
) -> list[SearchHit]:
    out: list[SearchHit] = []
    for url in urls:
        u = url.strip()
        if not u.startswith(("http://", "https://")):
            continue
        out.append(
            SearchHit(
                url=_normalize_url(u),
                title=title,
                snippet=snippet,
                from_dork=None,
            )
        )
    return out


def dedupe_hits(hits: list[SearchHit]) -> list[SearchHit]:
    seen: set[str] = set()
    out: list[SearchHit] = []
    for hit in hits:
        key = _normalize_url(hit.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out
