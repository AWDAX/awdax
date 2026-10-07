"""
One place that starts Chrome for every part of the backend (page inspection, rendering, the data-feed and download readers, the
eGazette scraper, Google search), so the flags a server needs are the same everywhere.

On a server Chrome usually runs as root inside a container or a service, where it will not start without `--no-sandbox`, and
`/dev/shm` is small, so `--disable-dev-shm-usage` is always set. Where Chrome or its driver is not on the default path
(a Docker image, a VM with Chromium), name them with CHROME_BIN and CHROMEDRIVER_PATH.
"""

from __future__ import annotations

import os
from typing import Any, Iterable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def chrome_options(
    *,
    headless: bool = True,
    window: str | None = "1920,1080",
    capture_network: bool = False,
    extra_args: Iterable[str] = (),
    prefs: dict[str, Any] | None = None,
    hide_automation: bool = False,
) -> Options:
    opts = Options()
    for arg in ("--no-sandbox", "--disable-dev-shm-usage", *extra_args):
        opts.add_argument(arg)
    if headless:
        opts.add_argument("--headless=new")
        if window:
            opts.add_argument(f"--window-size={window}")
    if capture_network:
        opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # the page's own data requests (data_feed)
    if prefs:
        opts.add_experimental_option("prefs", prefs)
    if hide_automation:
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
    binary = (os.getenv("CHROME_BIN") or "").strip()
    if binary:
        opts.binary_location = binary
    return opts


def launch(**kwargs: Any) -> webdriver.Chrome:
    """A running Chrome (see chrome_options for the arguments)."""
    driver_path = (os.getenv("CHROMEDRIVER_PATH") or "").strip()
    service = Service(executable_path=driver_path) if driver_path else None
    return webdriver.Chrome(options=chrome_options(**kwargs), service=service) if service else webdriver.Chrome(options=chrome_options(**kwargs))
