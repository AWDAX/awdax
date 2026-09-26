"""Filter search hits before wasting browser time on junk domains."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from discovery.schemas import SearchHit

_BLOCK_HOST_SUFFIXES = (
    "wikipedia.org",
    "britannica.com",
    "electrical4u.com",
    "quora.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "reddit.com",
    "pinterest.com",
    "instagram.com",
    "tiktok.com",
)

# Utility / gov portals that often appear for vague "electric" queries
_BLOCK_HOST_CONTAINS = (
    "mahadiscom",
    "discom",
    "parivahan.gov.in",  # registration portal, not price catalogs
)

_AUTOMOTIVE_HOST_SUFFIXES = (
    "cardekho.com",
    "carwale.com",
    "zigwheels.com",
    "autocarindia.com",
    "bikewale.com",
    "91wheels.com",
    "carandbike.com",
)

_EV_GOAL_RE = re.compile(
    r"\b(ev|electric|vehicle|car|auto|scooter)\b.*\b(india|indian)\b"
    r"|\b(india|indian)\b.*\b(ev|electric|vehicle|car|auto|scooter)\b",
    re.I,
)


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_blocked_url(url: str) -> bool:
    h = _host(url)
    if any(h == s or h.endswith(f".{s}") for s in _BLOCK_HOST_SUFFIXES):
        return True
    return any(part in h for part in _BLOCK_HOST_CONTAINS)


def is_automotive_catalog_url(url: str) -> bool:
    h = _host(url)
    if not any(h == s or h.endswith(f".{s}") for s in _AUTOMOTIVE_HOST_SUFFIXES):
        return False
    path = urlparse(url).path.lower()
    return any(
        k in path
        for k in (
            "electric",
            "ev",
            "car",
            "price",
            "new-cars",
            "newcars",
            "finder",
        )
    ) or h.endswith(("cardekho.com", "carwale.com", "zigwheels.com"))


def score_hit(user_goal: str, hit: SearchHit) -> int:
    if is_blocked_url(hit.url):
        return -100
    score = 0
    blob = f"{hit.title} {hit.snippet} {hit.url}".lower()
    goal = user_goal.lower()

    if is_automotive_catalog_url(hit.url):
        score += 12

    for word in ("price", "ex-showroom", "electric", "ev", "model", "variant"):
        if word in blob:
            score += 2

    if _EV_GOAL_RE.search(goal):
        if any(s in _host(hit.url) for s in _AUTOMOTIVE_HOST_SUFFIXES):
            score += 8
        if "electricity" in blob and "vehicle" not in blob and "car" not in blob:
            score -= 8

    if hit.from_dork is None:
        score += 1  # seeds / targeted queries

    return score


def filter_and_rank_hits(user_goal: str, hits: list[SearchHit]) -> list[SearchHit]:
    scored = [(score_hit(user_goal, h), h) for h in hits]
    scored = [(s, h) for s, h in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored]
