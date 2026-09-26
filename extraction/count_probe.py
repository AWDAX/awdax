"""Count probable list rows in DOM before full extraction."""

from __future__ import annotations

import logging

from inspector.browser import browser_session

logger = logging.getLogger(__name__)

_COUNT_JS = """
(args) => {
  const { containers, rowSel } = args;
  for (const sel of containers) {
    const root = document.querySelector(sel);
    if (!root) continue;
    const n = root.querySelectorAll(rowSel).length;
    if (n > 0) return { count: n, container: sel };
  }
  return { count: 0, container: null };
}
"""


def count_probable_rows(
    url: str,
    list_container: str,
    row_selector: str,
) -> int:
    containers = [s.strip() for s in list_container.split(",") if s.strip()]
    if not containers or not row_selector:
        return 0
    try:
        with browser_session() as page:
            page.goto(url, wait_until="domcontentloaded", timeout=55_000)
            page.wait_for_timeout(1200)
            for _ in range(3):
                page.evaluate("window.scrollBy(0, window.innerHeight)")
                page.wait_for_timeout(350)
            result = page.evaluate(
                _COUNT_JS,
                {"containers": containers, "rowSel": row_selector},
            )
            return int(result.get("count") or 0)
    except Exception as exc:
        logger.warning("Row count probe failed for %s: %s", url, exc)
        return 0
