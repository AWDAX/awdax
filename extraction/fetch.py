"""HTTP vs headless HTML fetch."""

from __future__ import annotations

import logging

import httpx
from playwright.sync_api import sync_playwright

from config.settings import settings

logger = logging.getLogger(__name__)


def fetch_http(url: str) -> tuple[str, bool]:
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=settings.http_probe_timeout,
            headers={"User-Agent": "AWDAX/1.0 (+data acquisition bot)"},
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text, True
    except Exception as exc:
        logger.warning("HTTP fetch failed %s: %s", url, exc)
        return "", False


def fetch_headless(url: str, *, scroll: bool = False) -> tuple[str, bool]:
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=settings.browser_timeout_ms)
            page.wait_for_timeout(1500)
            if scroll:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                page.wait_for_timeout(800)
            html = page.content()
            browser.close()
            return html, True
    except Exception as exc:
        logger.warning("Headless fetch failed %s: %s", url, exc)
        return "", False
