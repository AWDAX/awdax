"""Extract rows from a live page (scroll + site scripts + generic cards)."""

from __future__ import annotations

import logging

from playwright.sync_api import sync_playwright

from config.settings import settings
from extractors.sites import extract_with_page

logger = logging.getLogger(__name__)

_GENERIC_EVAL = """
() => {
  const rows = [];
  const seen = new Set();
  const priceRe = /(₹[\\d,.]+|Rs\\.?\\s*[\\d,.]+(?:\\s*-\\s*[\\d,.]+)?\\s*(?:Lakh|lac)?)/i;
  document.querySelectorAll('article, li, div[class*="card" i]').forEach(card => {
    const link = card.querySelector('a[href*="car"], a[title]');
    const model = link ? (link.getAttribute('title') || link.textContent || '').trim() : '';
    if (!model || model.length < 3 || model.length > 100) return;
    if (!/[a-zA-Z]{2}/.test(model)) return;
    const m = (card.textContent || '').match(priceRe);
    if (!m) return;
    const key = model + m[0];
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ model, ex_showroom_price: m[0], brand: '' });
  });
  return rows;
}
"""


def _scroll_lazy(page) -> None:
    for _ in range(6):
        page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 600))")
        page.wait_for_timeout(500)


def extract_dom(url: str, *, selectors: str | None = None) -> list[dict[str, str]]:
    """Load URL in headless browser and pull structured car rows from DOM."""
    rows: list[dict[str, str]] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page.goto(url, wait_until="domcontentloaded", timeout=min(settings.browser_timeout_ms + 15_000, 60_000))
            page.wait_for_timeout(1200)
            _scroll_lazy(page)

            rows = extract_with_page(page, url)
            if len(rows) < 5:
                extra = page.evaluate(_GENERIC_EVAL)
                rows.extend(extra)

            if selectors:
                try:
                    custom = page.evaluate(
                        """(sel) => {
                          const rows = [];
                          document.querySelectorAll(sel).forEach(el => {
                            const t = (el.textContent || '').replace(/\\s+/g,' ').trim();
                            if (t.length > 10) rows.push({ model: t.slice(0,120), ex_showroom_price: '', brand: '' });
                          });
                          return rows;
                        }""",
                        selectors.split(",")[0].strip(),
                    )
                    rows.extend(custom)
                except Exception:
                    pass

            browser.close()
    except Exception as exc:
        logger.warning("DOM extract failed for %s: %s", url, exc)
    return rows
