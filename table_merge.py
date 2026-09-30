"""
Merge per-source scrape rows into one canonical table (e.g. car name + price).
"""

from __future__ import annotations

import json
import re
from typing import Any

from reasoning import ScrapeIntent, gemini_json

_NAME_ALIASES = (
    "car_name",
    "model",
    "name",
    "vehicle",
    "model_name",
    "car",
    "title",
    "subject",
    "Model",
    "Car Name",
    "Car",
    "Models",
)
_PRICE_ALIASES = (
    "price",
    "price_inr",
    "price (inr)",
    "ex_showroom_price",
    "ex_showroom",
    "on_road_price",
    "on_road",
    "starting_price",
    "price_inr",
    "Price",
    "Ex-Showroom Price",
    "Ex Showroom",
    "On Road Price",
)
_RANGE_ALIASES = ("range", "range_km", "driving_range", "Range", "Battery Range")
_BATTERY_ALIASES = ("battery", "battery_kwh", "Battery", "Battery Capacity")


def intent_avoid_oem_sites(intent: ScrapeIntent) -> bool:
    blob = " ".join(
        [
            intent.topic,
            intent.raw_prompt,
            " ".join(intent.constraints),
            " ".join(intent.entity_types),
        ]
    ).lower()
    if any(
        k in blob
        for k in (
            "avoid oem",
            "avoid vendor",
            "avoid manufacturer",
            "no oem",
            "not brand",
            "all ev",
            "all electric",
            "every ev",
            "list all",
            "with prices",
            "comparison",
            "compare",
        )
    ):
        return True
    if "list" in blob and ("car" in blob or "ev" in blob or "vehicle" in blob):
        return True
    return any("aggregator" in c.lower() or "avoid" in c.lower() and "oem" in c.lower() for c in intent.constraints)


def is_oem_source(*, source_category: str = "", domain: str = "", url: str = "") -> bool:
    cat = (source_category or "").lower()
    if cat in ("manufacturer", "oem"):
        return True
    host = (domain or url or "").lower()
    for hint in (
        "tatamotors",
        "hyundai.com",
        "mgmotor",
        "mahindraelectric",
        "mahindra.com",
        "byd.com",
        "marutisuzuki",
        "kia.com",
        "mercedes-benz",
        "bmw.in",
        "audi.in",
        "volkswagen",
        "skoda-auto",
        "nissan.in",
        "renault.co.in",
        "tesla.com",
    ):
        if hint in host:
            return True
    return False


def default_columns(intent: ScrapeIntent) -> list[str]:
    fields = [f.strip() for f in (intent.output_fields or []) if f.strip()]
    if fields:
        return [_slug_header(f) for f in fields]
    topic = (intent.topic or "").lower()
    if "ev" in topic or "car" in topic or "vehicle" in topic:
        return ["car_name", "price", "range_km", "battery", "source"]
    return ["name", "value", "source"]


def _slug_header(label: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", label.strip().lower()).strip("_")
    return s or "field"


def _pick(row: dict[str, Any], aliases: tuple[str, ...]) -> str:
    for key in aliases:
        if key in row and str(row[key]).strip():
            return str(row[key]).strip()
    lower_map = {str(k).lower(): v for k, v in row.items()}
    for key in aliases:
        v = lower_map.get(key.lower())
        if v is not None and str(v).strip():
            return str(v).strip()
    for k, v in row.items():
        if k.startswith("_") or k in ("PDF_URL", "PDF_Text", "id"):
            continue
        kl = str(k).lower()
        for alias in aliases:
            if alias.lower() in kl and str(v).strip():
                return str(v).strip()
    return ""


def _normalize_name(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    n = re.sub(r"[^a-z0-9\s]", "", n)
    return n


def _merge_row_key(row: dict[str, str], columns: list[str]) -> str:
    brand = _normalize_name(row.get("brand") or "")
    name = _normalize_name(row.get("car_name") or row.get("name") or row.get(columns[0]) if columns else "")
    if brand and name.startswith(brand):
        name = name[len(brand) :].strip()
    combined = f"{brand} {name}".strip() if brand else name
    return re.sub(r"\s+", "", combined) or name or brand


def _row_from_record(data: dict[str, Any], source_url: str, columns: list[str]) -> dict[str, str]:
    out: dict[str, str] = {c: "" for c in columns}
    name = _pick(data, _NAME_ALIASES)
    price = _pick(data, _PRICE_ALIASES)
    rng = _pick(data, _RANGE_ALIASES)
    battery = _pick(data, _BATTERY_ALIASES)

    if "car_name" in columns:
        out["car_name"] = name
    elif "name" in columns:
        out["name"] = name
    if "price" in columns:
        out["price"] = price
    if "range_km" in columns:
        out["range_km"] = rng
    if "battery" in columns:
        out["battery"] = battery
    if "source" in columns:
        host = source_url
        if "://" in source_url:
            from urllib.parse import urlparse

            host = urlparse(source_url).netloc or source_url
        out["source"] = host.replace("www.", "")

    for col in columns:
        if out.get(col):
            continue
        slug = col.replace("_", " ")
        for k, v in data.items():
            if str(k).lower().replace("_", " ") == slug and str(v).strip():
                out[col] = str(v).strip()
                break

    if not name and not price:
        for k, v in data.items():
            if k.startswith("_") or k in ("PDF_URL", "PDF_Text"):
                continue
            if str(v).strip() and len(str(v)) < 200:
                if not out.get(columns[0]):
                    out[columns[0]] = str(v).strip()
                break
    return out


def merge_records(
    intent: ScrapeIntent,
    records: list[dict[str, Any]],
    *,
    use_ai: bool = True,
    columns_override: list[str] | None = None,
    column_labels_override: list[str] | None = None,
) -> dict[str, Any]:
    """
    records: each {data_json dict, source_url str}
    Returns {columns, rows, row_count}.
    """
    columns = columns_override or default_columns(intent)
    merged: dict[str, dict[str, str]] = {}

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

    catalog_prices = intent_expects_priced_catalog(intent.raw_prompt, intent.topic)

    for rec in records:
        data = rec.get("data") or rec.get("data_json") or {}
        if isinstance(data, str):
            data = json.loads(data)
        source_url = str(rec.get("source_url") or "")
        row = _row_from_record(data, source_url, columns)
        if not filter_vehicle_rows([row], columns, catalog_with_prices=catalog_prices):
            continue
        key = _merge_row_key(row, columns)
        if not key:
            key = _normalize_name(str(data.get("_row_key") or "")) or f"row_{len(merged)}"
        if key not in merged:
            merged[key] = row
            continue
        existing = merged[key]
        for col in columns:
            if not existing.get(col) and row.get(col):
                existing[col] = row[col]
            elif col == "price" and row.get(col) and _looks_like_price(row[col]) and not _looks_like_price(existing.get(col, "")):
                existing[col] = row[col]

    rows = [r for r in merged.values() if any(v for v in r.values())]
    rows.sort(key=lambda r: (r.get("car_name") or r.get("name") or "").lower())

    if use_ai and rows and len(rows) <= 120:
        rows = _ai_refine_table(intent, columns, rows)

    if intent_wants_full_catalog(intent):
        rows = coverage_backfill(intent, rows, columns)

    labels = column_labels_override or [_header_label(c) for c in columns]
    return {"columns": columns, "column_labels": labels, "rows": rows, "row_count": len(rows)}


def intent_wants_full_catalog(intent: ScrapeIntent) -> bool:
    from listing_sources import intent_wants_ev_catalog

    return intent_wants_ev_catalog(intent)


def coverage_backfill(
    intent: ScrapeIntent,
    rows: list[dict[str, str]],
    columns: list[str],
) -> list[dict[str, str]]:
    """Add missing EV nameplates from reference list when scrape under-counts."""
    if not intent_wants_full_catalog(intent):
        return rows
    target_min = int(__import__("os").getenv("EV_CATALOG_TARGET_MIN", "50"))
    if len(rows) >= target_min:
        return rows

    reference_names: list[dict[str, str]] = []
    try:
        from discovery import fetch_html

        ref_url = "https://en.wikipedia.org/wiki/Electric_car_use_in_India"
        html = (fetch_html(ref_url).get("html") or "")[:150000]
        name_col = "car_name" if "car_name" in columns else (columns[0] if columns else "name")
        prompt = f"""From this Wikipedia HTML/text, list electric passenger car MODELS sold or available in India.
Return JSON {{ "models": [ {{ "brand": "", "{name_col}": "" }} ] }}
Only real production models; include as many as the article lists.

HTML excerpt:
{html[:90000]}"""
        data = gemini_json(prompt)
        if isinstance(data, dict) and isinstance(data.get("models"), list):
            for m in data["models"]:
                if isinstance(m, dict) and (m.get(name_col) or m.get("car_name") or m.get("name")):
                    reference_names.append(
                        {
                            "brand": str(m.get("brand") or "").strip(),
                            name_col: str(m.get(name_col) or m.get("car_name") or m.get("name") or "").strip(),
                        }
                    )
    except Exception:
        pass

    if not reference_names:
        try:
            prompt = f"""List electric passenger car models currently available for sale in India (~55-65 models).
User goal: {intent.raw_prompt or intent.topic}
Return JSON {{ "models": [ {{ "brand": "", "car_name": "" }} ] }}"""
            data = gemini_json(prompt)
            if isinstance(data, dict) and isinstance(data.get("models"), list):
                for m in data["models"]:
                    if isinstance(m, dict):
                        reference_names.append(
                            {
                                "brand": str(m.get("brand") or "").strip(),
                                "car_name": str(m.get("car_name") or m.get("name") or "").strip(),
                            }
                        )
        except Exception:
            return rows

    by_key = {_merge_row_key(r, columns): r for r in rows}
    name_col = "car_name" if "car_name" in columns else columns[0]
    for ref in reference_names:
        stub: dict[str, str] = {c: "" for c in columns}
        stub[name_col] = ref.get(name_col) or ref.get("car_name") or ""
        if "brand" in columns:
            stub["brand"] = ref.get("brand") or ""
        if "source_url" in columns:
            stub["source_url"] = "reference/wikipedia+gemini"
        elif "source" in columns:
            stub["source"] = "reference"
        if not stub.get(name_col):
            continue
        from row_quality import is_junk_vehicle_name

        if is_junk_vehicle_name(stub.get(name_col) or ""):
            continue
        key = _merge_row_key(stub, columns)
        if key in by_key:
            existing = by_key[key]
            for c in columns:
                if not existing.get(c) and stub.get(c):
                    existing[c] = stub[c]
            continue
        by_key[key] = stub

    out = list(by_key.values())
    out.sort(key=lambda r: (r.get("brand") or "", r.get(name_col) or ""))
    return out


def _looks_like_price(s: str) -> bool:
    return bool(re.search(r"[\d,]+|\blakh\b|\bcr\b|₹|rs\.?", (s or "").lower()))


def _header_label(col: str) -> str:
    return col.replace("_", " ").strip().title()


def _ai_refine_table(intent: ScrapeIntent, columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    try:
        prompt = f"""You normalize scraped rows into a clean table for: {intent.topic}
Desired columns (keys): {json.dumps(columns)}

Rules:
- Merge duplicate vehicles (same model, spelling variants).
- Prefer price from aggregator sites over Wikipedia or empty.
- Drop FAQ questions, article headlines, and any row whose name ends with ? or starts with Which/What/Why/How.
- Drop rows that are clearly not vehicles (navigation, ads).
- Keep real model nameplates even if price is empty.
- Keep source column as site hostname.

Input rows:
{json.dumps(rows[:80], indent=2)}

Return JSON object: {{ "rows": [ object with exactly these keys: {columns} ] }}"""
        data = gemini_json(prompt)
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            cleaned: list[dict[str, str]] = []
            for item in data["rows"]:
                if not isinstance(item, dict):
                    continue
                row = {c: str(item.get(c) or "").strip() for c in columns}
                if row.get("car_name") or row.get("name"):
                    cleaned.append(row)
            if cleaned:
                return cleaned
    except Exception:
        pass
    return rows
