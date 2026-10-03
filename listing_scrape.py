"""
Scroll a listing page to the bottom so lazily loaded rows are in the HTML.
"""

from __future__ import annotations

import os
import time


def selenium_scroll_and_get_html(driver, *, max_scrolls: int | None = None) -> str:
    max_scrolls = max_scrolls or int(os.getenv("LISTING_MAX_SCROLLS", "18"))
    pause = float(os.getenv("LISTING_SCROLL_PAUSE", "1.0"))
    last_h = 0
    for _ in range(max_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        h = driver.execute_script("return document.body.scrollHeight") or 0
        if h == last_h:
            break
        last_h = h
    return driver.page_source or ""
