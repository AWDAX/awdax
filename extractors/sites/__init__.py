"""Host-specific Playwright extractors."""

from __future__ import annotations

from urllib.parse import urlparse

from playwright.sync_api import Page

from extractors.sites import cardekho, carwale


def extract_with_page(page: Page, url: str) -> list[dict[str, str]]:
    host = urlparse(url).netloc.lower()
    if "cardekho.com" in host:
        return cardekho.extract_page(page)
    if "carwale.com" in host:
        return carwale.extract_page(page)
    return []
