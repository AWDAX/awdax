"""
Exhaustive listing extraction: JSON blobs, scroll, multi-pass merge.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

from reasoning import ScrapeIntent

logger = logging.getLogger(__name__)

_MODEL_KEYS = frozenset(
    {
        "modelname",
        "model_name",
        "model",
        "carname",
        "car_name",
        "name",
        "title",
        "variantname",
        "displayname",
    }
)
_PRICE_KEYS = frozenset(
    {"price", "exshowroomprice", "ex_showroom_price", "onroadprice", "minprice", "maxprice", "price_range"}
)
_BRAND_KEYS = frozenset({"brand", "brandname", "make", "makename", "manufacturer", "oemname"})
_RANGE_KEYS = frozenset({"range", "rangekm", "drivingrange", "range_km", "arai_range"})
_BATTERY_KEYS = frozenset({"battery", "batterycapacity", "battery_kwh", "kwh"})


def _norm_key(k: str) -> str:
    return re.sub(r"[^a-z0-9]", "", k.lower())


def _first_str(obj: dict[str, Any], keys: frozenset[str]) -> str:
    for k, v in obj.items():
        if _norm_key(k) in keys and v is not None:
            s = str(v).strip()
            if s and s.lower() not in ("null", "none"):
                return s
    return ""


def _map_vehicle_dict(obj: dict[str, Any], columns: list[str]) -> dict[str, str] | None:
    name = _first_str(obj, _MODEL_KEYS)
    if not name or len(name) < 2 or len(name) > 120:
        return None
    from row_quality import is_junk_vehicle_name

    brand = _first_str(obj, _BRAND_KEYS)
    price = _first_str(obj, _PRICE_KEYS)
    if is_junk_vehicle_name(name, has_price=bool(price)):
        return None
    rng = _first_str(obj, _RANGE_KEYS)
    battery = _first_str(obj, _BATTERY_KEYS)

    row: dict[str, str] = {c: "" for c in columns}
    col_map = {
        "car_name": name,
        "name": name,
        "brand": brand,
        "price": price,
        "price_inr": price,
        "range_km": rng,
        "battery": battery,
        "battery_capacity_kwh": battery,
        "charging_time_hours": _first_str(obj, frozenset({"chargingtime", "chargetime"})),
    }
    for c in columns:
        if col_map.get(c):
            row[c] = col_map[c]
    if not row.get(columns[0] if columns else "car_name"):
        row[columns[0] if columns else "car_name"] = name
    if brand and "brand" in columns:
        row["brand"] = brand
    return row if name else None


def _walk_collect_vehicles(obj: Any, out: list[dict[str, Any]], depth: int = 0) -> None:
    if depth > 25:
        return
    if isinstance(obj, dict):
        keys_norm = {_norm_key(k) for k in obj.keys()}
        if keys_norm & _MODEL_KEYS and (keys_norm & (_PRICE_KEYS | _BRAND_KEYS | _RANGE_KEYS) or len(obj) >= 3):
            out.append(obj)
        for v in obj.values():
            _walk_collect_vehicles(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj[:500]:
            _walk_collect_vehicles(item, out, depth + 1)


def extract_from_embedded_json(html: str, columns: list[str]) -> list[dict[str, str]]:
    blobs: list[Any] = []

    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            blobs.append(json.loads(block.strip()))
        except Exception:
            continue

    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    if m:
        try:
            blobs.append(json.loads(m.group(1)))
        except Exception:
            pass

    for m in re.finditer(r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;", html, re.S):
        try:
            blobs.append(json.loads(m.group(1)[:500000]))
        except Exception:
            continue

    raw_objects: list[dict[str, Any]] = []
    for blob in blobs:
        _walk_collect_vehicles(blob, raw_objects)

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for obj in raw_objects:
        mapped = _map_vehicle_dict(obj, columns)
        if not mapped:
            continue
        key = _row_dedupe_key(mapped, columns)
        if key in seen:
            continue
        seen.add(key)
        rows.append(mapped)
    return rows


def _row_dedupe_key(row: dict[str, str], columns: list[str]) -> str:
    brand = (row.get("brand") or "").lower()
    name = (row.get("car_name") or row.get("name") or row.get(columns[0]) or "").lower()
    name = re.sub(r"\s+", " ", name)
    if brand and name.startswith(brand):
        name = name[len(brand) :].strip()
    return re.sub(r"[^a-z0-9]", "", f"{brand}{name}")


def merge_row_lists(*lists: list[dict[str, str]], columns: list[str]) -> list[dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for lst in lists:
        for row in lst:
            if not isinstance(row, dict):
                continue
            key = _row_dedupe_key(row, columns)
            if not key:
                continue
            if key not in merged:
                merged[key] = dict(row)
                continue
            for c in columns:
                if not merged[key].get(c) and row.get(c):
                    merged[key][c] = row[c]
    return list(merged.values())


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


def extract_listing_exhaustive(
    html: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
) -> list[dict[str, str]]:
    from html_extract import ai_extract_rows_from_html, extract_rows_from_page_html, rows_from_tables

    json_rows = extract_from_embedded_json(html, columns)
    table_rows = rows_from_tables(html, columns)
    generic_rows = extract_rows_from_page_html(html, intent, columns, page_url=page_url)

    combined = merge_row_lists(json_rows, table_rows, generic_rows, columns=columns)

    min_target = int(os.getenv("LISTING_MIN_ROWS", "35"))
    if len(combined) < min_target and len(html) > 5000:
        ai_rows = ai_extract_rows_from_html(html, intent, columns, page_url=page_url)
        combined = merge_row_lists(combined, ai_rows, columns=columns)

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

    catalog_prices = intent_expects_priced_catalog(intent.raw_prompt, intent.topic)
    return filter_vehicle_rows(combined, columns, catalog_with_prices=catalog_prices)
