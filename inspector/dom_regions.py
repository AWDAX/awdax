"""Locate data-rich DOM regions (ids, lists, tables) in headless browser."""

from __future__ import annotations

import json
import logging

from discovery.scrape_schema import DomRegionHint
from inspector.browser import browser_session

logger = logging.getLogger(__name__)

_SCAN_JS = """
() => {
  const regions = [];
  const seen = new Set();
  const priceRe = /(₹|rs\\.?|lakh|lac|ex-showroom|on-road|price)/i;
  const dataRe = /(electric|ev|car|model|variant|battery|range)/i;

  function score(el) {
    const text = (el.innerText || '').slice(0, 4000);
    let s = 0;
    if (priceRe.test(text)) s += 3;
    if (dataRe.test(text)) s += 2;
    const rows = el.querySelectorAll('li, tr, [class*="card" i], article').length;
    s += Math.min(rows, 40) / 4;
    const links = el.querySelectorAll('a[href]').length;
    if (links >= 3) s += 2;
    return { s, rows, links, text };
  }

  const nodes = document.querySelectorAll('[id], section, main, [data-section], [class*="list" i], table');
  for (const el of nodes) {
    if (!(el instanceof HTMLElement)) continue;
    const { s, rows, links, text } = score(el);
    if (s < 3 || rows < 2) continue;
    let selector = '';
    if (el.id) selector = '#' + CSS.escape(el.id);
    else if (el.getAttribute('data-section')) selector = `[data-section="${el.getAttribute('data-section')}"]`;
    else continue;
    if (seen.has(selector)) continue;
    seen.add(selector);
    const sampleLinks = [...el.querySelectorAll('a[href]')].slice(0, 5).map(a => a.href);
    regions.push({
      selector,
      element_id: el.id || '',
      tag: el.tagName,
      estimated_rows: rows,
      sample_text: text.slice(0, 220).replace(/\\s+/g, ' '),
      sample_links: sampleLinks,
      score: s,
    });
  }
  regions.sort((a, b) => b.score - a.score);
  return regions.slice(0, 12);
}
"""


def scan_dom_regions(url: str) -> list[DomRegionHint]:
    try:
        with browser_session() as page:
            page.goto(url, wait_until="domcontentloaded", timeout=55_000)
            page.wait_for_timeout(1500)
            for _ in range(4):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(350)
            raw = page.evaluate(_SCAN_JS)
    except Exception as exc:
        logger.warning("DOM region scan failed for %s: %s", url, exc)
        return []

    hints: list[DomRegionHint] = []
    for item in raw or []:
        hints.append(
            DomRegionHint(
                selector=item.get("selector") or "",
                element_id=item.get("element_id") or "",
                tag=item.get("tag") or "",
                estimated_rows=int(item.get("estimated_rows") or 0),
                sample_text=item.get("sample_text") or "",
                sample_links=list(item.get("sample_links") or []),
            )
        )
    return [h for h in hints if h.selector]
