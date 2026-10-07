"""
Reads the website a Google Maps listing points to, for the contact details and facts the listing does not have.

For each business with a website: the homepage and, only if it shows no email, its contact page. From them: a contact
email, the contact page, Instagram / Facebook / LinkedIn / WhatsApp links, what the site is built with, and plain
problems with it (no HTTPS, not mobile friendly, a copyright year years out of date). That last part is what a web
developer wants to know about a prospect.

Polite and safe: every fetch goes through url_guard.safe_get (no private addresses, every redirect checked, bodies
capped), robots.txt is honoured, a site is read once however many listings share it, and a run has a cap on sites and on
time. It reads the HTML the server sends; a site that draws everything with JavaScript gives little, and says so.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from urllib3.exceptions import InsecureRequestWarning

from url_guard import UnresolvableHost, UnsafeURL, safe_get

logger = logging.getLogger(__name__)

BOT_NAME = "AWDAXBot"
USER_AGENT = f"Mozilla/5.0 (compatible; {BOT_NAME}/1.0)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5", "Accept-Language": "en"}
MAX_PAGE_BYTES = 600_000
MAX_ROBOTS_BYTES = 100_000
OUTDATED_AFTER_YEARS = 3

# Columns this step adds to a Maps table (key -> label), in table order.
SITE_COLUMNS: list[tuple[str, str]] = [
    ("email", "Email"),
    ("contact_page", "Contact page"),
    ("instagram", "Instagram"),
    ("facebook", "Facebook"),
    ("linkedin", "LinkedIn"),
    ("whatsapp", "WhatsApp"),
    ("site_platform", "Website built with"),
    ("site_status", "Website status"),
    ("site_notes", "Website issues"),
]
SITE_KEYS = [k for k, _ in SITE_COLUMNS]

# A "website" that is really a social page, a listing or Google's own profile: nothing to read, but worth recording.
_SOCIAL_HOSTS = ("facebook.com", "fb.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com", "wa.me", "linktr.ee")
_LISTING_HOSTS = (
    "google.com", "goo.gl", "g.page", "business.site", "zomato.com", "swiggy.com", "justdial.com", "tripadvisor.com", "tripadvisor.in",
    "booking.com", "makemytrip.com", "practo.com", "urbancompany.com", "magicpin.in", "dineout.co.in", "sulekha.com", "indiamart.com",
)

# What a site is built with, from what it LOADS or declares (assets, a generator tag), never from a mere link to a platform's
# own website: python.org links to Blogger and is not built with it.
_PLATFORMS: list[tuple[str, re.Pattern[str]]] = [
    ("WordPress", re.compile(r"wp-content/|wp-includes/|<meta[^>]+generator[^>]+wordpress", re.I)),
    ("Wix", re.compile(r"static\.wixstatic\.com|parastorage\.com|<meta[^>]+generator[^>]+wix\.com", re.I)),
    ("Shopify", re.compile(r"cdn\.shopify\.com|shopify\.theme|Shopify\.shop\b", re.I)),
    ("Squarespace", re.compile(r"static1\.squarespace\.com|squarespace-cdn\.com|<meta[^>]+generator[^>]+squarespace", re.I)),
    ("Webflow", re.compile(r"data-wf-page|website-files\.com|<meta[^>]+generator[^>]+webflow", re.I)),
    ("GoDaddy Website Builder", re.compile(r"img1\.wsimg\.com|<meta[^>]+generator[^>]+godaddy", re.I)),
    ("Weebly", re.compile(r"editmysite\.com|weebly\.com/uploads", re.I)),
    ("Blogger", re.compile(r"<meta[^>]+generator[^>]+blogger|blogger\.com/static/", re.I)),
    ("Joomla", re.compile(r"<meta[^>]+generator[^>]+joomla|/media/jui/", re.I)),
    ("Drupal", re.compile(r"<meta[^>]+generator[^>]+drupal|/sites/default/files/", re.I)),
    ("Magento", re.compile(r"mage/cookies|<meta[^>]+generator[^>]+magento|/static/frontend/", re.I)),
]

_EMAIL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._%+-]{0,63}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}")
_JUNK_DOMAINS = {
    "example.com", "example.org", "domain.com", "email.com", "yourdomain.com", "yoursite.com", "mysite.com", "website.com", "company.com",
    "sentry.io", "wixpress.com", "sentry-next.wixpress.com", "godaddy.com", "squarespace.com", "shopify.com", "wordpress.com",
}
_JUNK_ENDINGS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".ico", ".woff", ".woff2", ".pdf", ".mp4")
_NO_REPLY = re.compile(r"no[-_.]?reply|do[-_.]?not[-_.]?reply|mailer-daemon|postmaster|abuse@|privacy@|unsubscribe", re.I)
_ROLE_ORDER = ["info", "contact", "hello", "hi", "enquiry", "enquiries", "inquiry", "sales", "support", "care", "office", "admin", "bookings", "booking", "reservations", "orders", "mail"]
_CONTACT_LINK = re.compile(r"contact|reach[- ]?us|get[- ]?in[- ]?touch|enquir|inquir|connect[- ]with", re.I)
_COPYRIGHT = re.compile(r"(?:©|&copy;|\(c\)|copyright)\s*(?:\d{4}\s*[-–—]\s*)?((?:19|20)\d{2})", re.I)


# ── reading one page ────────────────────────────────────────────────────────────────────────────────────────────

class _Page(HTMLParser):
    """The parts of a page this step needs: title, description, links, readable text, mailto and protected emails."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.meta: dict[str, str] = {}
        self.links: list[tuple[str, str]] = []
        self.text: list[str] = []
        self.cfemails: list[str] = []
        self._skip = 0
        self._in_title = False
        self._anchor: list[Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            if name and a.get("content"):
                self.meta.setdefault(name, a["content"].strip())
        elif tag == "a":
            if a.get("href"):
                self._anchor = [a["href"].strip(), []]
        if a.get("data-cfemail"):
            self.cfemails.append(a["data-cfemail"])

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "a" and self._anchor is not None:
            self.links.append((self._anchor[0], " ".join(self._anchor[1]).strip()))
            self._anchor = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.text.append(text)
            if self._anchor is not None:
                self._anchor[1].append(text)


def _decode_cfemail(hexed: str) -> str | None:
    """Cloudflare's email protection: the first byte is a key, the rest are the address XOR-ed with it."""
    try:
        raw = bytes.fromhex(hexed)
        return bytes(b ^ raw[0] for b in raw[1:]).decode("utf-8")
    except (ValueError, IndexError, UnicodeDecodeError):
        return None


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _emails_in(text: str) -> list[str]:
    text = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", text, flags=re.I)
    return _EMAIL.findall(text)


def _good_email(address: str) -> bool:
    address = address.lower()
    local, _, domain = address.partition("@")
    if not local or not domain or len(address) > 80 or address.endswith(_JUNK_ENDINGS) or not _EMAIL.fullmatch(address):
        return False
    if domain in _JUNK_DOMAINS or any(domain.endswith("." + d) for d in ("wixpress.com", "sentry.io")):
        return False
    return not _NO_REPLY.search(address)


def pick_email(found: list[str], site_host: str) -> str:
    """The best contact address: on the site's own domain first, then a role people write to (info, contact, sales...)."""
    seen: list[str] = []
    for e in found:
        e = e.strip().strip(".,;:").lower()
        if _good_email(e) and e not in seen:
            seen.append(e)
    if not seen:
        return ""

    def rank(item: tuple[int, str]) -> tuple[int, int, int]:
        order, e = item
        local, _, domain = e.partition("@")
        own = 0 if site_host and (domain == site_host or site_host.endswith("." + domain) or domain.endswith("." + site_host)) else 1
        role = next((i for i, r in enumerate(_ROLE_ORDER) if local == r or local.startswith(r)), len(_ROLE_ORDER))
        return own, role, order

    return min(enumerate(seen), key=rank)[1]


def _social(url: str) -> tuple[str, str] | None:
    """(kind, clean profile link) for a link to a business profile; None for share buttons, posts and other pages."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    segs = [s for s in parts.path.split("/") if s]
    if host.endswith("instagram.com") and segs and segs[0].lower() not in {"p", "reel", "reels", "explore", "accounts", "stories", "tv", "share", "direct"}:
        return "instagram", f"https://www.instagram.com/{segs[0]}/"
    if host in ("facebook.com", "fb.com", "m.facebook.com", "web.facebook.com") or host.endswith(".facebook.com"):
        if segs and segs[0].lower() == "profile.php" and parse_qs(parts.query).get("id"):
            return "facebook", f"https://www.facebook.com/profile.php?id={parse_qs(parts.query)['id'][0]}"
        if segs and segs[0].lower() not in {"sharer", "sharer.php", "share", "share.php", "dialog", "plugins", "tr", "login", "l.php", "policies", "help", "events", "hashtag", "watch"}:
            return "facebook", f"https://www.facebook.com/{segs[0]}"
    if host.endswith("linkedin.com") and len(segs) >= 2 and segs[0].lower() in {"company", "in", "school"}:
        return "linkedin", f"https://www.linkedin.com/{segs[0].lower()}/{segs[1]}"
    if host == "wa.me" and segs and segs[0].isdigit():
        return "whatsapp", f"https://wa.me/{segs[0]}"
    if host == "api.whatsapp.com" and parse_qs(parts.query).get("phone"):
        digits = re.sub(r"\D", "", parse_qs(parts.query)["phone"][0])
        if digits:
            return "whatsapp", f"https://wa.me/{digits}"
    return None


def _platform(html: str) -> str:
    head = html[:300_000]
    return next((name for name, pattern in _PLATFORMS if pattern.search(head)), "")


@dataclass
class _Read:
    emails: list[str]
    socials: dict[str, str]
    contact_page: str
    platform: str
    year: int | None
    mobile: bool
    text_len: int
    final_url: str


def _read_page(html: str, base_url: str) -> _Read:
    page = _Page()
    try:
        page.feed(html)
        page.close()
    except Exception:  # a page that breaks the parser still has its text so far
        logger.debug("HTML parse stopped early for %s", base_url)
    emails = _emails_in(" ".join(page.text))
    socials: dict[str, str] = {}
    contact = ""
    own = _host(base_url)
    for href, label in page.links:
        low = href.lower()
        if low.startswith("mailto:"):
            emails += _emails_in(href[7:].split("?")[0])
            continue
        if low.startswith(("javascript:", "tel:", "#", "data:")):
            continue
        absolute = urljoin(base_url, href)
        social = _social(absolute)
        if social:
            socials.setdefault(social[0], social[1])
            continue
        if not contact and _host(absolute) == own and (_CONTACT_LINK.search(urlsplit(absolute).path) or _CONTACT_LINK.search(label)):
            contact = absolute.split("#")[0]
    for hexed in page.cfemails:
        decoded = _decode_cfemail(hexed)
        if decoded:
            emails.append(decoded)
    years = [int(y) for y in _COPYRIGHT.findall(" ".join(page.text))]
    return _Read(
        emails=emails, socials=socials, contact_page=contact, platform=_platform(html),
        year=max(years) if years else None, mobile="viewport" in page.meta, text_len=len(" ".join(page.text)), final_url=base_url,
    )


# ── fetching ────────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass
class Fetched:
    url: str  # where it ended up, after redirects
    status: int
    text: str


Fetch = Callable[[str, int, float, bool], Fetched]


def default_fetch(url: str, max_bytes: int, timeout: float, verify: bool = True) -> Fetched:
    with warnings.catch_warnings():
        if not verify:  # the caller chose to read a site with a bad certificate and records that; the warning adds nothing
            warnings.simplefilter("ignore", InsecureRequestWarning)
        resp = safe_get(url, timeout=timeout, verify=verify, headers=HEADERS, max_bytes=max_bytes)
    return Fetched(str(resp.url), int(resp.status_code), resp.text or "")


class Robots:
    """robots.txt per host, read once. A missing, broken or unreachable one allows everything."""

    def __init__(self, fetch: Fetch | None = None, timeout: float = 5.0) -> None:
        self._fetch, self._timeout = fetch or default_fetch, timeout
        self._rules: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        key = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            known = key in self._rules
        if not known:
            rules: RobotFileParser | None = None
            try:
                got = self._fetch(f"{key}/robots.txt", MAX_ROBOTS_BYTES, self._timeout, True)
                if got.status < 400 and got.text.strip():
                    rules = RobotFileParser()
                    rules.parse(got.text.splitlines())
            except Exception:  # unreachable, blocked, odd encoding: no rules
                rules = None
            with self._lock:
                self._rules[key] = rules
        with self._lock:
            rules = self._rules[key]
        return True if rules is None else rules.can_fetch(BOT_NAME, url)


def _normalise(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url.lstrip("/")
    return url


def _blank() -> dict[str, str]:
    return {k: "" for k in SITE_KEYS}


def _is_host(host: str, names: tuple[str, ...]) -> bool:
    return any(host == n or host.endswith("." + n) for n in names)


def read_site(url: str, *, fetch: Fetch | None = None, robots: Robots | None = None, timeout: float = 10.0, now_year: int | None = None) -> dict[str, str]:
    """What the site at `url` tells us, as the SITE_KEYS columns. Never raises: a problem becomes `site_status`."""
    fetch = fetch or default_fetch
    out = _blank()
    url = _normalise(url)
    if not url:
        out["site_status"] = "no website"
        return out
    host = _host(url)
    if not host or "." not in host:
        out["site_status"] = "not a usable web address"
        return out

    social = _social(url)
    if _is_host(host, _SOCIAL_HOSTS):
        out["site_status"] = "social page only"
        if social:
            out[social[0]] = social[1]
        return out
    if _is_host(host, _LISTING_HOSTS):
        out["site_status"] = "listing page, not its own website"
        return out

    robots = robots or Robots(fetch)
    if not robots.allows(url):
        out["site_status"] = "not read: the site asks bots to stay out (robots.txt)"
        return out

    notes: list[str] = []
    try:
        got = _get(fetch, url, timeout, notes)
    except UnresolvableHost:
        out["site_status"] = "unreachable (the web address does not exist)"
        out["site_notes"] = "the listed website no longer exists"
        return out
    except UnsafeURL:
        out["site_status"] = "not read: address not allowed"
        out["site_notes"] = "the listed website does not lead to a working server"
        return out
    except requests.RequestException as exc:
        out["site_status"] = f"unreachable ({type(exc).__name__.replace('Error', '').replace('Exception', '') or 'network'})"
        return out
    except Exception:
        out["site_status"] = "unreachable"
        return out
    if got.status >= 400 and not (got.status in (401, 403) and len(got.text) > 800):
        out["site_status"] = f"unreachable (HTTP {got.status})"
        if got.status in (404, 410):
            out["site_notes"] = "the listed web page is gone"
        return out

    read = _read_page(got.text, got.url)
    emails = list(read.emails)
    socials = dict(read.socials)
    contact = read.contact_page
    # The contact page only when the homepage showed no usable email: one more request for most of the value.
    if not pick_email(emails, host) and contact and robots.allows(contact):
        try:
            more = _get(fetch, contact, timeout, [])
            if more.status < 400:
                extra = _read_page(more.text, more.url)
                emails += extra.emails
                for kind, link in extra.socials.items():
                    socials.setdefault(kind, link)
        except Exception:
            logger.debug("contact page not read: %s", contact)

    year_now = now_year or datetime.now(timezone.utc).year
    if not urlsplit(got.url).scheme == "https":
        notes.insert(0, "no HTTPS")
    if not read.mobile:
        notes.append("not mobile friendly")
    if read.year and read.year <= year_now - OUTDATED_AFTER_YEARS:
        notes.append(f"looks outdated (© {read.year})")
    if read.text_len < 300:
        notes.append("almost no readable text (may need JavaScript)")
    out.update(
        email=pick_email(emails, host),
        contact_page=contact,
        instagram=socials.get("instagram", ""),
        facebook=socials.get("facebook", ""),
        linkedin=socials.get("linkedin", ""),
        whatsapp=socials.get("whatsapp", ""),
        site_platform=read.platform,
        site_status="read",
        site_notes="; ".join(notes),
    )
    return out


def _get(fetch: Fetch, url: str, timeout: float, notes: list[str]) -> Fetched:
    """One page. A broken HTTPS certificate is read anyway (small business sites often have one) and noted."""
    try:
        return fetch(url, MAX_PAGE_BYTES, timeout, True)
    except requests.exceptions.SSLError:
        got = fetch(url, MAX_PAGE_BYTES, timeout, False)
        notes.append("HTTPS certificate problem")
        return got


# Statuses that mean the listing's website is gone for good (not a slow or bot-blocking one): to a web developer the business
# has no website, however Google Maps lists one.
_DEAD = ("unreachable (the web address does not exist)", "unreachable (HTTP 404)", "unreachable (HTTP 410)", "not read: address not allowed")


def is_dead_site(row: dict[str, str]) -> bool:
    return str(row.get("site_status") or "").startswith(_DEAD)


def is_weak_site(row: dict[str, str]) -> bool:
    """A site that was read and has something to fix."""
    return row.get("site_status") == "read" and bool(row.get("site_notes"))


# ── a run's worth of sites ─────────────────────────────────────────────────────────────────────────────────────

def enrich(
    rows: list[dict[str, str]],
    *,
    read: Callable[..., dict[str, str]] | None = None,
    fetch: Fetch | None = None,
    workers: int = 8,
    max_sites: int = 150,
    time_budget_s: float = 150.0,
    timeout: float = 10.0,
    clock: Callable[[], float] = time.monotonic,
    on_batch: Callable[[int, int], None] | None = None,
    check_alive: Callable[[], None] | None = None,
) -> dict[str, int]:
    """Fill the SITE_KEYS columns of `rows` (best leads first), in place. One read per site, however many listings share it.

    Stops starting new sites at `max_sites` or when the time budget is spent; rows it did not reach say so in
    site_status. `on_batch(done, total)` runs on the calling thread after each batch, so the caller can save progress.
    Returns counts: sites read, with an email, failed, skipped."""
    read = read or read_site
    fetch = fetch or default_fetch
    for row in rows:
        for key in SITE_KEYS:
            row.setdefault(key, "")
    todo: list[dict[str, str]] = []
    for row in rows:
        if not (row.get("website") or "").strip():
            row["site_status"] = "no website"
        else:
            todo.append(row)
    robots = Robots(fetch)
    by_host: dict[str, list[dict[str, str]]] = {}
    for row in todo:
        by_host.setdefault(_host(_normalise(row["website"])) or row["website"], []).append(row)
    hosts = list(by_host)
    stats = {"sites": len(hosts), "read": 0, "emails": 0, "failed": 0, "skipped": 0}
    started = clock()
    done_hosts = 0

    def reach(host: str) -> tuple[str, dict[str, str]]:
        return host, read(by_host[host][0]["website"], fetch=fetch, robots=robots, timeout=timeout)

    step = max(1, workers) * 2
    limit = min(len(hosts), max(0, max_sites))

    def skip(rest: list[str]) -> None:
        for host in rest:
            for row in by_host[host]:
                row["site_status"] = "not read (this run's website limit was reached)"
            stats["skipped"] += 1

    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="sites") as pool:
        for start in range(0, limit, step):
            if check_alive:
                check_alive()
            if clock() - started > time_budget_s:
                skip(hosts[start:])
                break
            batch = hosts[start : min(start + step, limit)]
            for host, info in pool.map(reach, batch):
                for row in by_host[host]:
                    row.update(info)
                stats["read"] += info["site_status"] == "read"
                stats["emails"] += bool(info["email"])
                stats["failed"] += info["site_status"].startswith(("unreachable", "not read"))
            done_hosts += len(batch)
            if on_batch:
                on_batch(done_hosts, len(hosts))
        else:
            skip(hosts[limit:])  # the loop ran to its end (no time-out break): whatever is past the cap was not read
    return stats
