"""Playwright-based page inspection."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx
from playwright.sync_api import Browser, Page, sync_playwright

from config.settings import settings

logger = logging.getLogger(__name__)

_DATA_PATH_RE = re.compile(
    r"(download|\.csv|\.xlsx?|\.pdf|/api/|statistics|dataset|data-|/data/|report)",
    re.I,
)
_LOGIN_RE = re.compile(r"\b(sign in|log in|login|password)\b", re.I)
_BINARY_SUFFIXES = (".pdf", ".zip", ".xlsx", ".xls", ".csv", ".doc", ".docx")
_SKIP_RELATED_PARTS = ("/policy/", "/csr", "/privacy", "/terms", "/legal/")


@dataclass
class PageProbe:
    url: str
    final_url: str
    title: str
    ok: bool
    error: str | None = None
    text_excerpt: str = ""
    table_count: int = 0
    download_links: list[str] = field(default_factory=list)
    data_links: list[str] = field(default_factory=list)
    has_password_field: bool = False
    login_hint: bool = False
    http_content_type: str | None = None


@dataclass
class SourceInspection:
    seed_url: str
    seed_title: str
    pages: list[PageProbe] = field(default_factory=list)

    @property
    def pages_inspected(self) -> int:
        return len(self.pages)


def _same_site(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return pa.netloc.lower().removeprefix("www.") == pb.netloc.lower().removeprefix("www.")


def _is_navigable(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    if not parsed.netloc:
        return False
    return True


def _is_binary_url(url: str, content_type: str | None = None) -> bool:
    lower = url.lower().split("?")[0]
    if any(lower.endswith(ext) for ext in _BINARY_SUFFIXES):
        return True
    if content_type:
        ct = content_type.lower()
        if "pdf" in ct or "octet-stream" in ct or "spreadsheet" in ct:
            return True
    return False


def _should_visit_related(url: str) -> bool:
    lower = url.lower()
    if _is_binary_url(url):
        return False
    if any(part in lower for part in _SKIP_RELATED_PARTS):
        return False
    return True


def _score_link(href: str) -> int:
    score = 0
    lower = href.lower()
    if _DATA_PATH_RE.search(lower):
        score += 3
    for ext in (".csv", ".xlsx", ".xls", ".pdf", ".json"):
        if lower.endswith(ext):
            score += 4
    return score


def _probe_http(url: str) -> str | None:
    try:
        with httpx.Client(follow_redirects=True, timeout=settings.http_probe_timeout) as client:
            resp = client.head(url)
            if resp.status_code >= 400:
                resp = client.get(url)
            return resp.headers.get("content-type")
    except Exception:
        return None


def _extract_links(page: Page, base_url: str) -> list[str]:
    hrefs: list[str] = []
    for el in page.query_selector_all("a[href]"):
        href = el.get_attribute("href")
        if not href:
            continue
        absolute = urljoin(base_url, href.strip())
        if _is_navigable(absolute):
            hrefs.append(absolute.split("#")[0])
    return hrefs


def probe_page(page: Page, url: str) -> PageProbe:
    content_type = _probe_http(url)
    if _is_binary_url(url, content_type):
        name = urlparse(url).path.split("/")[-1] or url
        return PageProbe(
            url=url,
            final_url=url,
            title=name,
            ok=True,
            text_excerpt="[Binary file — use HTTP/file download extractor, not page navigation.]",
            download_links=[url],
            http_content_type=content_type,
        )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms)
        page.wait_for_timeout(800)
        final_url = page.url
        title = page.title() or url
        text = page.inner_text("body")[:4000] if page.query_selector("body") else ""
        tables = page.locator("table").count()
        pwd = page.locator('input[type="password"]').count() > 0
        login_hint = bool(_LOGIN_RE.search(text[:1500]))

        all_links = _extract_links(page, final_url)
        downloads: list[str] = []
        data_links: list[str] = []
        seen: set[str] = set()
        for link in all_links:
            if link in seen:
                continue
            seen.add(link)
            lower = link.lower()
            if any(lower.endswith(ext) for ext in (".csv", ".xlsx", ".xls", ".pdf", ".json", ".zip")):
                downloads.append(link)
            elif _score_link(link) > 0 and _same_site(url, link):
                data_links.append(link)

        return PageProbe(
            url=url,
            final_url=final_url,
            title=title,
            ok=True,
            text_excerpt=text,
            table_count=tables,
            download_links=downloads[:15],
            data_links=data_links[:20],
            has_password_field=pwd,
            login_hint=login_hint,
            http_content_type=content_type,
        )
    except Exception as exc:
        logger.warning("Page probe failed for %s: %s", url, exc)
        return PageProbe(
            url=url,
            final_url=url,
            title=url,
            ok=False,
            error=str(exc),
            http_content_type=content_type,
        )


def inspect_source(
    page: Page,
    seed_url: str,
    *,
    max_related: int | None = None,
) -> SourceInspection:
    max_related = max_related if max_related is not None else settings.browser_max_related_links
    root = probe_page(page, seed_url)
    inspection = SourceInspection(seed_url=seed_url, seed_title=root.title, pages=[root])
    if not root.ok:
        return inspection

    related = [link for link in root.data_links if _should_visit_related(link)]
    ranked = sorted(set(related), key=_score_link, reverse=True)
    for link in ranked[:max_related]:
        if link.rstrip("/") == seed_url.rstrip("/"):
            continue
        inspection.pages.append(probe_page(page, link))
    return inspection


@contextmanager
def browser_session():
    with sync_playwright() as pw:
        browser: Browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page.set_default_timeout(settings.browser_timeout_ms)
            yield page
        finally:
            browser.close()


def inspect_candidates(urls: list[str]) -> list[SourceInspection]:
    """Visit each candidate URL and related data links in one browser session."""
    if not urls:
        return []
    out: list[SourceInspection] = []
    try:
        with browser_session() as page:
            for url in urls:
                out.append(inspect_source(page, url))
    except Exception:
        logger.exception("Headless browser session failed")
    return out
