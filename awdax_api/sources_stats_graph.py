from __future__ import annotations

import re
import math
from typing import Any
from urllib.parse import urlparse

from awdax_api.dataset_export import build_dataset_table
from awdax_api.orchestrator import is_running


def build_sources_response(sess: dict[str, Any]) -> dict[str, Any]:
    sources = sess.get("sources") or []
    plans = sess.get("plans") or []
    table = build_dataset_table(sess, limit=5000)
    url_counts: dict[str, int] = {}
    if table and "source_url" in (table.get("columns") or []):
        idx = table["columns"].index("source_url")
        for row in table.get("rows") or []:
            u = str(row[idx] if idx < len(row) else "").strip()
            if u:
                url_counts[u] = url_counts.get(u, 0) + 1

    out_sources: list[dict[str, Any]] = []
    for i, plan in enumerate(plans):
        p = plan if isinstance(plan, dict) else {}
        url = p.get("source_url") or p.get("entry_url") or ""
        domain = urlparse(url).netloc
        src_meta = (
            sources[i].to_dict()
            if i < len(sources) and hasattr(sources[i], "to_dict")
            else (sources[i] if i < len(sources) and isinstance(sources[i], dict) else {})
        )
        if isinstance(src_meta, dict):
            url = src_meta.get("url") or url
            domain = src_meta.get("domain") or domain
        accepted = url_counts.get(url, 0)
        status = "blocked" if p.get("blocked") else ("complete" if accepted else "validated")
        out_sources.append(
            {
                "id": str(i + 1),
                "url": url,
                "title": p.get("source_name") or domain or url,
                "status": status,
                "accepted": accepted,
                "partial": 0,
                "rejected": 0,
                "reason": (p.get("warnings") or [""])[0] if p.get("blocked") else "",
                "domain": domain,
                "origin": "search",
                "rank_score": p.get("confidence"),
                "rank_reasons": [],
                "deep_accepted": 0,
                "deep_notes": [],
                "linked_from": None,
            }
        )

    seen = {item["url"] for item in out_sources}
    for item in sess.get("discovery_sources") or []:
        if not isinstance(item, dict) or not item.get("url") or item["url"] in seen:
            continue
        out_sources.append(item)
        seen.add(item["url"])

    accepted_count = sum(s["accepted"] for s in out_sources)
    return {
        "candidate_count": len(out_sources),
        "sources": out_sources,
        "raw_count": accepted_count,
        "partial_count": 0,
        "accepted_count": accepted_count,
        "rejected_count": sum(1 for s in out_sources if s["status"] == "blocked"),
        "research_outcome": "complete" if accepted_count else "in_progress",
    }


def build_dataset_stats(sess: dict[str, Any]) -> dict[str, Any]:
    table = build_dataset_table(sess, limit=5000)
    if not table:
        return {
            "row_count": 0,
            "column_count": 0,
            "fill_rate": 0.0,
            "tier_counts": {},
            "mean_score": None,
            "inferred_periods": 0,
            "explicit_periods": 0,
            "source_count": 0,
            "period_min": None,
            "period_max": None,
        }
    rows = table.get("rows") or []
    cols = table.get("columns") or []
    filled = sum(1 for row in rows for cell in row if str(cell).strip())
    total_cells = max(1, len(rows) * max(1, len(cols)))
    return {
        "row_count": len(rows),
        "column_count": len(cols),
        "fill_rate": round(filled / total_cells, 4),
        "tier_counts": {"unscored": len(rows)},
        "mean_score": None,
        "inferred_periods": 0,
        "explicit_periods": 0,
        "source_count": len(sess.get("plans") or []),
        "period_min": None,
        "period_max": None,
    }


_MISSING = {"", "-", "--", "—", "n/a", "na", "null", "none", "unknown"}
_SCALES = {"k": 1e3, "thousand": 1e3, "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "crore": 1e7, "crores": 1e7, "million": 1e6, "billion": 1e9}
_NUMBER = re.compile(r"^([+-]?(?:\d[\d,]*(?:\.\d+)?|\.\d+))\s*([a-z][a-z0-9 /.-]{0,15})?%?$", re.I)
_DURATION = re.compile(r"^(?:(\d+(?:\.\d+)?)\s*(?:hours?|hrs?|h))?\s*(?:(\d+(?:\.\d+)?)\s*(?:minutes?|mins?|m))?\s*(?:(\d+(?:\.\d+)?)\s*(?:seconds?|secs?|s))?$", re.I)
_ID_COLUMN = re.compile(r"(^|[_\s-])(id|no|serial|rank|index|year|date|month|period|quarter)([_\s-]|$)", re.I)


def _measure(value: Any) -> tuple[float, str] | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw.lower() in _MISSING:
        return None
    duration = _DURATION.fullmatch(raw)
    if duration and any(part is not None for part in duration.groups()):
        hours, minutes, seconds = (float(part or 0) for part in duration.groups())
        total = hours * 60 + minutes + seconds / 60
        return (total, "min") if math.isfinite(total) else None
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1].strip()
    raw = re.sub(r"^(?:₹|\$|€|£|rs\.?|inr\b|usd\b|eur\b|gbp\b)\s*", "", raw, flags=re.I)
    match = _NUMBER.fullmatch(raw)
    if not match:
        return None
    digits, suffix = match.groups()
    percent = raw.endswith("%")
    if "," in digits and not re.fullmatch(r"[+-]?\d{1,3}(?:,\d{2,3})+\.?(?:\d+)?", digits):
        return None
    if "," in digits and len(digits.split(",")[-1].split(".")[0]) != 3:
        return None
    try:
        number = float(digits.replace(",", ""))
    except ValueError:
        return None
    if suffix:
        words = suffix.lower().split(maxsplit=1)
        scale = _SCALES.get(words[0])
        if scale:
            number *= scale
            suffix = words[1] if len(words) > 1 else ""
        if suffix and (not re.fullmatch(r"[a-z][a-z0-9 /.-]{0,15}", suffix, re.I) or re.search(r"\d", suffix)):
            return None
    result = -number if negative else number
    return (result, "%" if percent else (suffix or "").lower()) if math.isfinite(result) else None


def _number(value: Any) -> float | None:
    measure = _measure(value)
    return measure[0] if measure else None


def _unit(table: dict[str, Any], index: int) -> str:
    units: dict[str, int] = {}
    for row in table.get("rows") or []:
        if index >= len(row):
            continue
        measure = _measure(row[index])
        if measure:
            units[measure[1]] = units.get(measure[1], 0) + 1
    return max(units, key=units.get) if units else ""


def _numeric_columns(table: dict[str, Any]) -> list[str]:
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    numeric: list[str] = []
    for i, name in enumerate(cols):
        if _ID_COLUMN.search(name) or name in {"source_url", "pdf_url"}:
            continue
        present = [row[i] for row in rows[:50] if i < len(row) and str(row[i]).strip().lower() not in _MISSING]
        hits = sum(_number(value) is not None for value in present)
        if present and hits >= max(1, math.ceil(len(present) * 0.8)):
            numeric.append(name)
    return numeric


def graph_parameters(sess: dict[str, Any], include_partial: bool = False) -> dict[str, Any]:
    _ = include_partial
    table = build_dataset_table(sess, limit=5000)
    if not table:
        return {"parameters": []}
    params = []
    for name in _numeric_columns(table):
        index = table["columns"].index(name)
        unit = _unit(table, index)
        params.append(
            {
                "name": name,
                "unit": unit,
                "points": sum((_measure(row[index]) or (None, None))[1] == unit for row in table.get("rows") or [] if len(row) > index),
                "x_kind": "category",
                "period_min": None,
                "period_max": None,
                "series_count": 1,
            }
        )
    return {"parameters": params}


def graph_charts(sess: dict[str, Any], parameters: list[str], include_partial: bool = False) -> dict[str, Any]:
    _ = include_partial
    table = build_dataset_table(sess, limit=5000)
    if not table:
        return {"charts": []}
    cols = table.get("columns") or []
    rows = table.get("rows") or []
    charts = []
    numeric = set(_numeric_columns(table))
    x_col = next((name for name in cols if name not in numeric and name not in {"source_url", "pdf_url"}), cols[0] if cols else "x")
    xi = cols.index(x_col) if x_col in cols else 0
    for param in parameters:
        if param not in numeric:
            continue
        pi = cols.index(param)
        unit = _unit(table, pi)
        points = []
        omitted = 0
        for ri, row in enumerate(rows):
            if pi >= len(row):
                continue
            raw = str(row[pi]).strip()
            measure = _measure(raw)
            if not measure or measure[1] != unit:
                if raw.lower() not in _MISSING:
                    omitted += 1
                continue
            val = measure[0]
            x = str(row[xi] if xi < len(row) else ri)
            points.append(
                {
                    "x": x,
                    "value": val,
                    "raw": raw,
                    "observation_id": str(ri),
                    "source_url": str(row[cols.index("source_url")]) if "source_url" in cols and cols.index("source_url") < len(row) else "",
                }
            )
        charts.append(
            {
                "parameter": param,
                "unit": unit,
                "type": "line",
                "x": x_col,
                "group": None,
                "series": [{"name": param, "points": points}],
                "omitted": omitted,
                "duplicates": 0,
            }
        )
    return {"charts": charts}


def rescore_dataset(sess: dict[str, Any]) -> dict[str, Any]:
    if is_running(sess["id"]):
        raise RuntimeError("Run in progress")
    table = build_dataset_table(sess, limit=5000)
    n = len(table.get("rows") or []) if table else 0
    return {"accepted": n, "partial": 0, "rejected": 0}
