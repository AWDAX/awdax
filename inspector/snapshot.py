"""Rich page snapshot from headless browser DOM."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from playwright.sync_api import Page

from inspector.browser import PageProbe, browser_session, inspect_source

_PRICE_RE = re.compile(r"(₹|rs\.?\s*\d|ex-showroom|on-road|price|\blakh\b)", re.I)


@dataclass
class PageStructure:
    headings: list[str] = field(default_factory=list)
    table_summaries: list[str] = field(default_factory=list)
    list_item_count: int = 0
    card_like_count: int = 0
    has_pagination: bool = False
    has_filters: bool = False
    download_links: list[str] = field(default_factory=list)
    sample_text: str = ""


@dataclass
class SiteSnapshot:
    url: str
    final_url: str
    title: str
    ok: bool
    error: str | None = None
    pages_opened: int = 1
    structure: PageStructure = field(default_factory=PageStructure)
    probes: list[PageProbe] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        s = self.structure
        payload = {
            "url": self.url,
            "final_url": self.final_url,
            "title": self.title,
            "ok": self.ok,
            "error": self.error,
            "pages_opened": self.pages_opened,
            "headings": s.headings[:12],
            "tables": s.table_summaries[:8],
            "list_items": s.list_item_count,
            "card_blocks": s.card_like_count,
            "pagination": s.has_pagination,
            "filters": s.has_filters,
            "downloads": s.download_links[:10],
            "sample_text": s.sample_text[:2500],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


def _collect_structure(page: Page, probe: PageProbe) -> PageStructure:
    structure = PageStructure(
        download_links=list(probe.download_links),
        sample_text=probe.text_excerpt[:2500],
    )
    try:
        structure.headings = page.eval_on_selector_all(
            "h1, h2, h3",
            "els => els.map(e => (e.innerText || '').trim()).filter(Boolean).slice(0, 15)",
        )
    except Exception:
        structure.headings = []

    try:
        structure.table_summaries = page.evaluate(
            """() => {
              const out = [];
              for (const t of document.querySelectorAll('table')) {
                const rows = t.querySelectorAll('tr');
                const headers = [];
                const first = t.querySelector('tr');
                if (first) {
                  for (const c of first.querySelectorAll('th, td')) {
                    const tx = (c.innerText || '').trim();
                    if (tx) headers.push(tx.slice(0, 40));
                  }
                }
                out.push(`rows=${rows.length} headers=${headers.slice(0, 8).join(' | ')}`);
                if (out.length >= 8) break;
              }
              return out;
            }"""
        )
    except Exception:
        structure.table_summaries = []

    try:
        structure.list_item_count = page.locator("ul li, ol li").count()
        structure.card_like_count = page.locator(
            '[class*="card"], [class*="Card"], article, [data-testid*="card"]'
        ).count()
        structure.has_pagination = (
            page.locator(
                '[class*="pagination"], nav[aria-label*="page" i], a[rel="next"], button:has-text("Next")'
            ).count()
            > 0
        )
        structure.has_filters = (
            page.locator('select, input[type="search"], [class*="filter"], [class*="Filter"]').count() > 2
        )
    except Exception:
        pass

    if _PRICE_RE.search(structure.sample_text):
        structure.headings.append("(detected price-related content in body text)")

    return structure


def capture_site_snapshot(url: str) -> SiteSnapshot:
    """Open URL in headless browser and capture what is visible on the page."""
    try:
        with browser_session() as page:
            inspection = inspect_source(page, url)
            if not inspection.pages:
                return SiteSnapshot(url=url, final_url=url, title=url, ok=False, error="No page data")
            root = inspection.pages[0]
            if not root.ok:
                return SiteSnapshot(
                    url=url,
                    final_url=root.final_url,
                    title=root.title,
                    ok=False,
                    error=root.error,
                    probes=inspection.pages,
                )
            page.goto(root.final_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_timeout(1200)
            structure = _collect_structure(page, root)
            for p in inspection.pages[1:]:
                structure.download_links.extend(p.download_links)
            structure.download_links = list(dict.fromkeys(structure.download_links))[:15]

            return SiteSnapshot(
                url=url,
                final_url=page.url,
                title=page.title() or root.title,
                ok=True,
                pages_opened=len(inspection.pages),
                structure=structure,
                probes=inspection.pages,
            )
    except Exception as exc:
        return SiteSnapshot(url=url, final_url=url, title=url, ok=False, error=str(exc))
