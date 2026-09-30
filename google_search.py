"""
Google Search via Selenium (human-style query → organic results).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

_SKIP_HOST_SUBSTR = (
    "google.",
    "gstatic.com",
    "youtube.com",
    "accounts.google",
    "support.google",
    "policies.google",
    "maps.google",
    "webcache.googleusercontent",
    "translate.google",
)


def create_google_driver(*, headless: bool | None = None) -> Any:
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium is not installed")
    if headless is None:
        headless = __import__("os").getenv("GOOGLE_SEARCH_HEADLESS", "1") != "0"
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1366,900")
    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(45)
    return driver


def _host_ok(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        return False
    if not host or not url.startswith("http"):
        return False
    return not any(s in host for s in _SKIP_HOST_SUBSTR)


def _unwrap_google_url(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("/url?"):
        qs = parse_qs(urlparse(href).query)
        if qs.get("q"):
            return unquote(qs["q"][0])
    return href


def _dismiss_consent(driver) -> None:
    selectors = [
        "button#L2AGLb",
        "button[aria-label*='Accept']",
        "button[aria-label*='accept']",
        "form[action*='consent'] button",
        "div.QS5gu button",
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            btn.click()
            time.sleep(0.8)
            return
        except Exception:
            continue


def _open_google_home(driver) -> None:
    driver.get("https://www.google.com/ncr")
    time.sleep(1.2)
    _dismiss_consent(driver)


def _find_search_box(driver):
    selectors = ["textarea[name='q']", "input[name='q']"]
    for sel in selectors:
        try:
            return WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
        except TimeoutException:
            continue
    raise RuntimeError("Google search box not found")


def _parse_organic_results(driver, *, max_results: int = 5) -> list[dict[str, str]]:
    time.sleep(1.0)
    hits: list[dict[str, str]] = []
    seen: set[str] = set()

    blocks = driver.find_elements(By.CSS_SELECTOR, "div.g, div[data-sokoban-container] div.Gx5Zad")
    if not blocks:
        blocks = driver.find_elements(By.CSS_SELECTOR, "#search div[data-hveid]")

    for block in blocks:
        if len(hits) >= max_results:
            break
        try:
            link_el = block.find_element(By.CSS_SELECTOR, "a[href]")
            href = _unwrap_google_url(link_el.get_attribute("href") or "")
            if not _host_ok(href):
                continue
            title = ""
            try:
                title = block.find_element(By.CSS_SELECTOR, "h3").text.strip()
            except Exception:
                title = (link_el.text or "").strip()[:200]
            snippet = ""
            try:
                snippet = block.find_element(By.CSS_SELECTOR, "div.VwiC3b, div[data-sncf]").text.strip()
            except Exception:
                snippet = ""
            if href in seen:
                continue
            seen.add(href)
            hits.append({"url": href, "title": title, "snippet": snippet})
        except Exception:
            continue

    if len(hits) < max_results:
        for link in driver.find_elements(By.CSS_SELECTOR, "#search a[href^='http']"):
            if len(hits) >= max_results:
                break
            href = _unwrap_google_url(link.get_attribute("href") or "")
            if not _host_ok(href) or href in seen:
                continue
            seen.add(href)
            title = link.text.strip()[:200]
            hits.append({"url": href, "title": title, "snippet": ""})

    return hits[:max_results]


def google_search(
    driver,
    query: str,
    *,
    max_results: int = 5,
) -> list[dict[str, str]]:
    """Run one Google query on an open driver; returns organic result dicts."""
    query = re.sub(r"\s+", " ", (query or "").strip())
    if not query:
        return []

    _open_google_home(driver)
    box = _find_search_box(driver)
    box.clear()
    box.send_keys(query)
    time.sleep(0.3)
    box.send_keys(Keys.RETURN)

    try:
        WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#search, div#rso")))
    except TimeoutException:
        logger.warning("Google results did not load for: %s", query)
        return []

    return _parse_organic_results(driver, max_results=max_results)


def google_search_batch(queries: list[str], *, max_results_per_query: int = 5) -> list[tuple[str, list[dict[str, str]]]]:
    driver = create_google_driver()
    out: list[tuple[str, list[dict[str, str]]]] = []
    try:
        for q in queries:
            try:
                hits = google_search(driver, q, max_results=max_results_per_query)
            except Exception as e:
                logger.warning("Google search failed for %r: %s", q, e)
                hits = []
            out.append((q, hits))
            time.sleep(float(__import__("os").getenv("GOOGLE_SEARCH_DELAY", "1.2")))
    finally:
        driver.quit()
    return out
