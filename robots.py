"""
robots.txt: a page a site asks crawlers not to read is skipped, and the source shows why ("permitted sources only").

One robots.txt per site, fetched through url_guard.safe_get (so it is SSRF-checked like every other request) and kept
for an hour. RFC 9309: no robots.txt (4xx) allows everything; a server error (5xx) or no answer allows nothing.
"""

from __future__ import annotations

import threading
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

from url_guard import UnsafeURL, safe_get

AGENT = "AWDAX"  # the name rules may address; `User-agent: *` rules apply to it too
TTL_S = 3600
FAILED_TTL_S = 60  # an unreachable robots.txt blocks the site only briefly: a blip must not cost a whole hour
MAX_SITES = 512
_cache: dict[str, tuple[float, RobotFileParser]] = {}  # origin -> (expires_at, rules)
_lock = threading.Lock()


class RobotsDisallowed(UnsafeURL):
    """The site's robots.txt asks crawlers not to read this page. Shown as the reason the source was skipped."""


def _rules_for(origin: str) -> RobotFileParser:
    with _lock:
        hit = _cache.get(origin)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
    rules = RobotFileParser()
    ttl = TTL_S
    try:
        try:
            r = safe_get(f"{origin}/robots.txt", timeout=8, max_bytes=512 * 1024)
        except requests.exceptions.SSLError:
            # As fetch_html does: some official sites (egazette.gov.in) serve a broken certificate chain. Only the
            # rules are read here, and a tampered file could at worst make a run skip a page.
            r = safe_get(f"{origin}/robots.txt", timeout=8, max_bytes=512 * 1024, verify=False)
        if r.status_code >= 500:
            rules.disallow_all = True
            ttl = FAILED_TTL_S
        elif r.status_code >= 400:
            rules.allow_all = True
        else:
            rules.parse((r.text or "").splitlines())
    except UnsafeURL:
        raise
    except Exception:
        rules.disallow_all = True  # unreachable: RFC 9309 says assume nothing is allowed
        ttl = FAILED_TTL_S
    now = time.monotonic()
    with _lock:
        if len(_cache) >= MAX_SITES:
            for key in [k for k, (expires, _) in _cache.items() if expires <= now]:
                del _cache[key]
            if len(_cache) >= MAX_SITES:
                _cache.clear()  # ponytail: drop-all when 512 live sites; an LRU if refetching ever shows up
        _cache[origin] = (now + ttl, rules)
    return rules


def check_robots(url: str) -> None:
    """Raise RobotsDisallowed when the site's robots.txt asks crawlers not to read `url`.

    ponytail: the stdlib parser applies the first matching rule, not RFC 9309's longest match, so an `Allow` listed
    after a broader `Disallow` is missed. That only ever skips a page a site allows, never reads one it forbids."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return  # url_guard refuses these anyway
    if not _rules_for(f"{parts.scheme}://{parts.netloc}").can_fetch(AGENT, url):
        raise RobotsDisallowed("Skipped: the site's robots.txt asks crawlers not to read this page")
