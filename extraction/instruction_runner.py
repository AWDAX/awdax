"""Execute ScrapeInstructionSet in headless browser."""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from discovery.scrape_schema import ScrapeInstructionSet
from inspector.browser import browser_session

logger = logging.getLogger(__name__)

_EXTRACT_LIST_JS = """
(args) => {
  const { containerSel, rowSel, fields, detailLinkSel } = args;
  const root = document.querySelector(containerSel);
  if (!root) return { error: 'container_not_found', rows: [] };
  const rows = [];
  root.querySelectorAll(rowSel).forEach(row => {
    const item = {};
    for (const f of fields) {
      const el = row.querySelector(f.selector);
      if (!el) { item[f.column] = ''; continue; }
      if (f.attr === 'href') item[f.column] = el.href || el.getAttribute('href') || '';
      else if (f.attr.startsWith('attr:')) item[f.column] = el.getAttribute(f.attr.slice(5)) || '';
      else item[f.column] = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    }
    const linkEl = row.querySelector(detailLinkSel || 'a[href]');
    item.__detail_url = linkEl ? linkEl.href : '';
    rows.push(item);
  });
  return { error: null, rows };
}
"""

_DETAIL_JS = """
(args) => {
  const fields = args.fields;
  const out = {};
  for (const f of fields) {
    const el = document.querySelector(f.selector);
    if (!el) { out[f.column] = ''; continue; }
    out[f.column] = (el.innerText || '').replace(/\\s+/g, ' ').trim();
  }
  return out;
}
"""


def run_instructions(instructions: ScrapeInstructionSet) -> list[dict[str, str]]:
    rows_out: list[dict[str, str]] = []
    fields_payload = [
        {"column": f.column, "selector": f.selector, "attr": f.attr} for f in instructions.fields
    ]

    try:
        with browser_session() as page:
            page.goto(instructions.source_url, wait_until="domcontentloaded", timeout=55_000)
            page.wait_for_timeout(1200)
            for _ in range(4):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(300)

            container_candidates = [s.strip() for s in instructions.list_container.split(",") if s.strip()]
            result = {"error": "container_not_found", "rows": []}
            for container_sel in container_candidates:
                result = page.evaluate(
                    _EXTRACT_LIST_JS,
                    {
                        "containerSel": container_sel,
                        "rowSel": instructions.row_selector,
                        "fields": fields_payload,
                        "detailLinkSel": instructions.detail_page.link_selector or "a[href]",
                    },
                )
                if not result.get("error") and result.get("rows"):
                    break
            if result.get("error"):
                logger.warning(
                    "List container miss %s on %s",
                    instructions.list_container,
                    instructions.source_url,
                )
                return []

            for raw in result.get("rows") or []:
                detail_url = raw.pop("__detail_url", "") or ""
                row = {k: str(v).strip() for k, v in raw.items()}
                rows_out.append(row)

            detail = instructions.detail_page
            if detail.enabled and detail.fields:
                detail_fields = [{"column": f.column, "selector": f.selector, "attr": f.attr} for f in detail.fields]
                visits = 0
                for row in rows_out:
                    if visits >= detail.max_visits:
                        break
                    link = row.get("detail_url") or row.get("url") or ""
                    if not link and detail.link_selector:
                        continue
                    if not link:
                        continue
                    try:
                        page.goto(link, wait_until="domcontentloaded", timeout=35_000)
                        page.wait_for_timeout(800)
                        extra = page.evaluate(_DETAIL_JS, {"fields": detail_fields})
                        for k, v in (extra or {}).items():
                            if v and not row.get(k):
                                row[k] = str(v).strip()
                        visits += 1
                    except Exception as exc:
                        logger.debug("Detail page skip %s: %s", link, exc)

    except Exception as exc:
        logger.warning("Instruction runner failed: %s", exc)

    return rows_out
