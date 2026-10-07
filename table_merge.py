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
    from row_quality import topic_is_vehicles

    # The manufacturer-site rule is about car catalogs. For any other topic it would skip, say, a university's page because
    # its domain looks like a car brand's; and "ev" must be a word ("development", "every" are not electric vehicles).
    if not topic_is_vehicles(intent.raw_prompt, intent.topic):
        return False
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
    if "list" in blob:
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
    from row_quality import topic_is_vehicles

    # Whole words only: "ev" in "development" or "car" in "career" must not turn a request into a car table.
    if topic_is_vehicles(intent.raw_prompt, intent.topic):
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


_DATE_OR_NUMBER = re.compile(
    r"[\d\s/\-.:,]+|\d{1,2}[-\s/][A-Za-z]{3,9}[-\s/,]+\d{2,4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9},?\s+\d{4}"
)


def _merge_row_key(row: dict[str, str], columns: list[str]) -> str:
    brand = _normalize_name(row.get("brand") or "")
    first = str(row.get(columns[0]) or "").strip() if columns else ""
    if not (brand or row.get("car_name") or row.get("name")) and first and _DATE_OR_NUMBER.fullmatch(first):
        # A first column holding a date or a number names no item: rows that share it are not the same thing.
        return "v" + row_value_key(row, columns)
    name = _normalize_name(row.get("car_name") or row.get("name") or row.get(columns[0]) if columns else "")
    if brand and name.startswith(brand):
        name = name[len(brand) :].strip()
    combined = f"{brand} {name}".strip() if brand else name
    return re.sub(r"\s+", "", combined) or name or brand


_NOT_IDENTITY = {"source", "source_url", "url", "link", "pdf_url", "pdf_text"}


def row_value_key(row: dict[str, Any], columns: list[str]) -> str:
    """A short key made of all of a row's values (source links left out), for telling apart rows whose name or id is
    shared: two debates on one date, two branches of one shop."""
    import hashlib

    cols = [c for c in (columns or sorted(k for k in row if not str(k).startswith("_"))) if str(c).lower() not in _NOT_IDENTITY]
    text = "|".join(_normalize_name(str(row.get(c) or "")) for c in cols)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


_LONG = 25  # characters: longer values are free text (titles), shorter ones are labels, names, scores


def _similar(a: str, b: str) -> bool | None:
    """Do two cells say the same thing? None when either is empty (nothing to compare)."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if not na or not nb:
        return None
    if na == nb or na.replace(" ", "") in nb.replace(" ", "") or nb.replace(" ", "") in na.replace(" ", ""):
        return True
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) / len(ta | tb) >= 0.5


def same_dated_item(a: dict[str, str], b: dict[str, str], columns: list[str]) -> bool:
    """Two rows with the same date from different sources describe one item (one final, written by two sites) when they
    agree on most other cells. Two long texts that differ (two debate titles) mean two items, whatever else agrees."""
    agree = disagree = 0
    for col in columns[1:]:
        if str(col).lower() in _NOT_IDENTITY:
            continue
        x, y = str(a.get(col) or ""), str(b.get(col) or "")
        same = _similar(x, y)
        if same is None:
            continue
        if same:
            agree += 1
        elif len(x) > _LONG and len(y) > _LONG:
            return False
        else:
            disagree += 1
    return agree >= 2 and agree / (agree + disagree) >= 0.6


def _merge_dated_duplicates(merged: dict[str, dict[str, str]], merged_from: dict[str, str], columns: list[str]) -> None:
    """Rows keyed by all their values (a date or number first column, see _merge_row_key) are distinct within a source,
    but the same item read from two sources should be one row: merge those, filling empty cells from the duplicate."""
    if not columns:
        return
    groups: dict[str, list[str]] = {}
    for key, row in merged.items():
        if key.startswith("v"):
            groups.setdefault(_normalize_name(str(row.get(columns[0]) or "")), []).append(key)
    for keys in groups.values():
        kept: list[str] = []
        for key in keys:
            row = merged[key]
            twin = next((k for k in kept if merged_from.get(k) != merged_from.get(key) and same_dated_item(merged[k], row, columns)), None)
            if twin is None:
                kept.append(key)
                continue
            for col in columns:
                if not merged[twin].get(col) and row.get(col):
                    merged[twin][col] = row[col]
            del merged[key]


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
    merged_from: dict[str, str] = {}  # key -> the source the row came from

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog, topic_is_vehicles

    catalog_prices = intent_expects_priced_catalog(intent.raw_prompt, intent.topic)
    vehicle = topic_is_vehicles(intent.raw_prompt, intent.topic)

    for rec in records:
        data = rec.get("data") or rec.get("data_json") or {}
        if isinstance(data, str):
            data = json.loads(data)
        source_url = str(rec.get("source_url") or "")
        row = _row_from_record(data, source_url, columns)
        if not filter_vehicle_rows([row], columns, catalog_with_prices=catalog_prices, vehicle=vehicle):
            continue
        key = _merge_row_key(row, columns)
        if not key:
            key = _normalize_name(str(data.get("_row_key") or "")) or f"row_{len(merged)}"
        if key in merged and merged_from.get(key) == source_url and any(
            (merged[key].get(c) or "") != (row.get(c) or "") for c in columns
        ):
            # Same name, same page, different values: two items (debates of one date), not one item seen twice. Rows with
            # the same name from different sources still merge below.
            key = f"{key}|{row_value_key(row, columns)}"
        if key not in merged:
            merged[key] = row
            merged_from[key] = source_url
            continue
        existing = merged[key]
        for col in columns:
            if not existing.get(col) and row.get(col):
                existing[col] = row[col]
            elif col == "price" and row.get(col) and _looks_like_price(row[col]) and not _looks_like_price(existing.get(col, "")):
                existing[col] = row[col]

    _merge_dated_duplicates(merged, merged_from, columns)
    rows = [r for r in merged.values() if any(v for v in r.values())]
    rows.sort(key=lambda r: (r.get("car_name") or r.get("name") or "").lower())

    # The AI clean-up only reads the first AI_REFINE_MAX rows and its prompt is about vehicles: for a longer table or any other
    # topic it would drop the rest or the right rows, so it is not used there.
    if use_ai and rows and len(rows) <= AI_REFINE_MAX and vehicle:
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

        ref_url = "https://en.wikipedia.org/wiki/Electric_vehicle_industry_in_India"
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
        # Only names read from the reference article are added. A list the model writes from memory is a guess, and a guess
        # does not belong in a table where every row must have a source.
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


AI_REFINE_MAX = 80


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
{json.dumps(rows[:AI_REFINE_MAX], indent=2)}

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
            # A clean-up removes a few junk rows and merges a few duplicates. One that removes most of the table has gone
            # wrong, so the rows as scraped are kept.
            if cleaned and len(cleaned) >= 0.7 * len(rows):
                return cleaned
    except Exception:
        pass
    return rows
