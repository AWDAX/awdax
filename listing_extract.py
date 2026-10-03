"""Listing pages to rows: tables from raw HTML and the per-source LLM listing extract (from scraper.py)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from discovery import fetch_html
from inspector import ScrapePlan
from reasoning import ScrapeIntent

logger = logging.getLogger(__name__)

from plan_scraper import PlanDrivenScraper  # noqa: E402


def _strip_html_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def extract_tables_from_html(html: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for block in re.findall(r"<table\b[^>]*>(.*?)</table>", html, re.I | re.S):
        headers = [_strip_html_tags(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", block, re.I | re.S)]
        headers = [h for h in headers if h]
        rows: list[list[str]] = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", block, re.I | re.S):
            if re.search(r"<th\b", tr, re.I):
                continue
            cells = [_strip_html_tags(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.I | re.S)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if headers or rows:
            tables.append({"headers": headers, "rows": rows})
    return tables


def _finalize_extract_rows(
    rows: list[dict[str, Any]],
    plan: ScrapePlan,
    *,
    intent: ScrapeIntent | None = None,
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    id_field = plan.id_field or "car_name"
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        brand = str(row.get("brand") or "").strip()
        car = str(row.get("car_name") or row.get("name") or "").strip()
        ext = (f"{brand}|{car}" if brand and car else "") or row.get(id_field) or car or row.get("_row_key") or ""
        if not ext:
            row[id_field] = f"row_{i}"
        elif not row.get(id_field):
            row[id_field] = str(ext)[:120]
        row.setdefault("PDF_URL", "")
        row.setdefault("PDF_Text", "")
        out.append(row)

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

    cols = columns or []
    catalog_prices = bool(intent and intent_expects_priced_catalog(intent.raw_prompt, intent.topic))
    return filter_vehicle_rows(out, cols or None, catalog_with_prices=catalog_prices)


def _extract_listing_rows(
    html: str,
    intent: ScrapeIntent,
    schema: dict[str, Any],
    *,
    page_url: str,
    plan: ScrapePlan,
) -> list[dict[str, Any]]:
    columns = schema.get("columns") or []
    if not columns:
        return []
    from gemini_scrape import gemini_extract_rows_from_page

    rows = gemini_extract_rows_from_page(
        html,
        intent,
        columns,
        page_url=page_url,
        source_name=plan.source_name,
        column_labels=schema.get("column_labels"),
    )
    return _finalize_extract_rows(rows, plan, intent=intent, columns=columns)


def _is_regulatory_table_plan(plan: ScrapePlan) -> bool:
    url = (plan.entry_url or plan.source_url or "").lower()
    return plan.table_selector == "#gvGazetteList" or "egazette.gov.in" in url


def _fetch_html_for_gemini(
    plan: ScrapePlan,
    source_url: str,
    *,
    scroll_listing: bool,
) -> str:
    fetched = fetch_html(source_url)
    html = fetched.get("html") or ""
    if not scroll_listing:
        return html

    scraper = PlanDrivenScraper(plan, fast_mode=os.getenv("SCRAPE_FAST", "1") == "1")
    scraper.setup_driver()
    try:
        scraper.open_entry()
        from listing_scrape import selenium_scroll_and_get_html

        return selenium_scroll_and_get_html(scraper.driver) or scraper.driver.page_source or html
    finally:
        scraper.quit()


def _should_exhaust_listing(url: str, intent: ScrapeIntent) -> bool:
    from listing_sources import intent_wants_ev_catalog, is_aggregator_listing_url

    if is_aggregator_listing_url(url):
        return True
    return intent_wants_ev_catalog(intent) and any(
        h in (url or "").lower() for h in ("carwale", "cardekho", "91wheels", "zigwheels", "wikipedia.org/wiki")
    )
