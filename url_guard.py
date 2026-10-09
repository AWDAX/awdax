"""
SSRF guard for every fetch of a URL that a user, the LLM or scraped page content chose.

* `check_url(url)`        - scheme + resolved-address check; raises `UnsafeURL`.
* `safe_get(url, ...)`    - `requests` GET that re-checks the URL and every redirect hop, optionally capping the body.
* `check_browser_url(d)`  - after a Selenium page load, verify where Chrome actually ended up.

Set `AWDAX_ALLOW_PRIVATE_URLS=1` to skip the address check (local development / tests that hit localhost).
It never relaxes the scheme check.

Known limitation: the name is resolved here and again by `requests` / Chrome, so a hostile DNS server can still
answer differently the second time (DNS rebinding); closing that needs connection-level IP pinning.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests

logger = logging.getLogger(__name__)

ENV_ALLOW_PRIVATE = "AWDAX_ALLOW_PRIVATE_URLS"
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_SIX_TO_FOUR = ipaddress.ip_network("2002::/16")

_MSG_ADDRESS = "Blocked: address not allowed"
_MSG_SCHEME = "Blocked: only http and https URLs are allowed"
_MSG_INVALID = "Blocked: invalid URL"


class UnsafeURL(ValueError):
    """The URL (or a redirect target) points somewhere the server must not fetch. The text is short and safe to show."""


class UnresolvableHost(UnsafeURL):
    """The host name did not resolve; a plain failure rather than a policy block."""


def host_is(url: str, host: str) -> bool:
    """True when the URL's host is `host` or a subdomain of it; never when `host` only appears in a path or query
    ("https://evil.example/?egazette.gov.in")."""
    try:
        h = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return False
    return h == host or h.endswith("." + host)


def _private_allowed() -> bool:
    return os.getenv(ENV_ALLOW_PRIVATE, "").strip().lower() in ("1", "true", "yes")


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip in _SIX_TO_FOUR:
        return ipaddress.IPv4Address((int(ip) >> 80) & 0xFFFFFFFF)
    return None


def _is_public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address):
        v4 = _embedded_v4(ip)
        if v4 is not None and not _is_public(str(v4)):
            return False
    return bool(
        ip.is_global
        and not ip.is_multicast  # is_global is True for 224.0.0.0/4
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_unspecified
        and not ip.is_reserved
    )


def _hostname_via_urllib3(url: str) -> str | None:
    """The host as requests/urllib3 will read it; None when urllib3 is unavailable."""
    try:
        from urllib3.util import parse_url
    except ImportError:  # pragma: no cover
        return None
    try:
        host = parse_url(url).host
    except Exception as exc:  # LocationParseError and friends
        raise UnsafeURL(_MSG_INVALID) from exc
    return (host or "").strip("[]").lower()


def _ascii_host(host: str) -> str:
    host = host.lower()
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def check_url(url: str) -> str:
    """Return `url` unchanged if it is http(s) and every address its host resolves to is globally routable."""
    if not isinstance(url, str) or not url:
        raise UnsafeURL(_MSG_INVALID)
    if any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in url):
        raise UnsafeURL(_MSG_INVALID)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL(_MSG_INVALID) from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeURL(_MSG_SCHEME)
    host = (parts.hostname or "").strip()
    if not host:
        raise UnsafeURL(_MSG_INVALID)
    # Both parsers must agree on the host, or `http://good.example\@127.0.0.1/`-style tricks could split them.
    other = _hostname_via_urllib3(url)
    if other is not None and _ascii_host(other) != _ascii_host(host):
        raise UnsafeURL(_MSG_INVALID)
    if _private_allowed():
        return url

    try:
        infos = socket.getaddrinfo(host, port or (443 if parts.scheme.lower() == "https" else 80), type=socket.SOCK_STREAM)
    except (OSError, UnicodeError) as exc:  # gaierror is an OSError
        raise UnresolvableHost("could not resolve host") from exc
    addrs = {str(info[4][0]) for info in infos}
    if not addrs:
        raise UnresolvableHost("could not resolve host")
    for addr in addrs:
        try:
            public = _is_public(addr)
        except ValueError:
            public = False
        if not public:
            logger.warning("SSRF guard blocked host %r (resolves to a non-public address)", host)
            raise UnsafeURL(_MSG_ADDRESS)
    return url


def _read_capped(resp: requests.Response, max_bytes: int) -> None:
    buf = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=16384):
            buf.extend(chunk)
            if len(buf) >= max_bytes:
                break
    finally:
        resp.close()
    resp._content = bytes(buf[:max_bytes])  # type: ignore[attr-defined]
    resp._content_consumed = True  # type: ignore[attr-defined]


def safe_get(
    url: str,
    *,
    max_redirects: int = 5,
    max_bytes: int | None = None,
    session: requests.Session | None = None,
    **kwargs: Any,
) -> requests.Response:
    """GET `url`, checking it and every redirect target with `check_url` before requesting it.

    Other keyword arguments (timeout, headers, verify, ...) go to `requests` unchanged; `allow_redirects` and
    `stream` are set here. Raises `UnsafeURL` for a blocked URL or hop, and `requests.TooManyRedirects` when the
    chain is longer than `max_redirects`. With `max_bytes` at most that many (decoded) bytes of the body are read, so
    `.content` / `.text` hold a truncated body and a huge page cannot exhaust memory. The returned response's `.url`
    is the last hop.
    """
    kwargs["allow_redirects"] = False
    kwargs["stream"] = True
    getter = session.get if session is not None else requests.get
    current = url
    for hop in range(max_redirects + 1):
        check_url(current)
        resp = getter(current, **kwargs)
        location = resp.headers.get("Location") if resp.status_code in _REDIRECT_CODES else None
        if not location:
            break
        resp.close()
        if hop >= max_redirects:
            raise requests.TooManyRedirects(f"Exceeded {max_redirects} redirects")
        current = urljoin(current, location)
    if max_bytes is not None:
        _read_capped(resp, max_bytes)
    else:
        try:
            resp.content  # noqa: B018 - stream=True, so read the body now like a normal GET
        finally:
            resp.close()
    return resp


def check_browser_url(driver: Any) -> None:
    """Raise `UnsafeURL` if the page the browser finished on (after its own redirects) is not allowed.

    Call right after a page load. Redirects Chrome followed cannot be vetted beforehand, so this catches them after
    the fact; the page content must not be read or used when it raises. `about:blank` holds no content and passes.
    """
    current = str(getattr(driver, "current_url", "") or "")
    if current.strip().lower() == "about:blank":
        return
    check_url(current)
