"""
Runs a checked question plan (ask_data.check_query) over a typed table and returns the answer, exactly.

The same operations as the app's browser engine (Frontend/src/analytics/aggregate.ts): filter, group, count / sum / average /
minimum / maximum / median / distinct, sort, top N. Money and quantities are exact decimals: a total over thousands of
rows matches the source to the last paisa. Cells that are not numbers are left out and reported, never read as 0.
Dates are grouped by the text as written (the browser's month/quarter bucketing is not repeated here).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from column_kinds import AVG_EXTRA, Column, Typed, group_key, is_missing, mean, median, parse_number, site_of

AGG_LABEL = {
    "count": "Count of rows", "sum": "Sum", "avg": "Average", "min": "Minimum", "max": "Maximum",
    "median": "Median", "distinct": "Distinct count",
}
OTHER_LABEL = "All rows"


def json_number(value: Decimal | None) -> int | float | None:
    """A decimal as a JSON number: a whole number stays an integer."""
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def _value_key(col: Column, row: int) -> tuple[str, str] | None:
    label = col.labels[row]
    if not label or is_missing(label):
        return None
    if col.kind == "url":
        site = site_of(label)
        return site, site
    return group_key(label), " ".join(label.split())


def _passes(t: Typed, f: dict[str, Any], row: int) -> bool:
    op = f["op"]
    if op == "search":
        needle = str(f["values"][0] if f.get("values") else "").strip().lower()
        return not needle or any(needle in cell.lower() for cell in t.raw[row])
    col = t.columns[f["column"]]
    if op == "present":
        return col.numbers[row] is not None if col.numbers is not None else bool(col.labels[row]) and not is_missing(col.labels[row])
    if op == "contains":
        return str(f["values"][0] if f.get("values") else "").lower() in col.labels[row].lower()
    if op in ("in", "notIn"):
        key = _value_key(col, row)
        hit = key is not None and key[0] in {group_key(v) for v in f["values"]}
        return hit if op == "in" else not hit
    value = col.numbers[row] if col.numbers is not None else None
    if value is None:
        return False

    def bound(i: int) -> Decimal | None:
        if i >= len(f["values"]):
            return None
        n = parse_number(f["values"][i])
        return n.value if n else None

    lo = bound(0)
    hi = bound(1) if op == "between" else bound(0)
    if op == "gte":
        return lo is not None and value >= lo
    if op == "lte":
        return hi is not None and value <= hi
    return lo is not None and hi is not None and lo <= value <= hi


def filter_rows(t: Typed, filters: list[dict[str, Any]]) -> list[int]:
    return [r for r in range(t.row_count) if all(_passes(t, f, r) for f in filters)]


def _reduce(agg: str, values: list[Decimal], rows: int, distinct: set[str], scale: int) -> Decimal | None:
    if agg == "count":
        return Decimal(rows)
    if agg == "distinct":
        return Decimal(len(distinct))
    if not values:
        return None
    if agg == "sum":
        return sum(values, Decimal(0))
    if agg == "avg":
        return mean(values, scale + AVG_EXTRA)
    if agg == "median":
        return median(values)
    if agg == "min":
        return min(values)
    return max(values)


def run_query(t: Typed, q: dict[str, Any]) -> dict[str, Any]:
    """The answer to one plan: {"columns": [...], "rows": [[label, value, rows_in_group], ...], "overall", "matched", "used", ...}."""
    agg = q["agg"]
    group = t.columns[q["groupBy"]] if q.get("groupBy") is not None else None
    measure = t.columns[q["measure"]] if q.get("measure") is not None else None
    needs_value = agg not in ("count", "distinct")
    filters = q.get("filters") or []
    matched = filter_rows(t, filters)

    buckets: dict[str, dict[str, Any]] = {}
    used_rows: list[int] = []
    blank = 0
    excluded: list[dict[str, Any]] = []
    for r in matched:
        g = _value_key(group, r) if group else ("all", OTHER_LABEL)
        if g is None:
            blank += 1
            continue
        value = None
        if needs_value:
            value = measure.numbers[r] if measure is not None and measure.numbers is not None else None
            if value is None:
                if measure is not None and r in measure.excluded:
                    excluded.append({"row": r, "column": measure.label, "value": measure.labels[r], "reason": measure.excluded[r]})
                else:
                    blank += 1
                continue
        b = buckets.setdefault(g[0], {"label": g[1], "values": [], "rows": [], "keys": set()})
        if value is not None:
            b["values"].append(value)
        b["rows"].append(r)
        if agg == "distinct" and measure is not None:
            k = _value_key(measure, r)
            if k:
                b["keys"].add(k[0])
        used_rows.append(r)

    scale = measure.scale if measure is not None else 0
    rows = [
        {"key": key, "label": b["label"], "value": _reduce(agg, b["values"], len(b["rows"]), b["keys"], scale), "count": len(b["rows"])}
        for key, b in buckets.items()
    ]
    sort = q.get("sort") or "value-desc"

    def by_value(x: dict[str, Any]) -> tuple[int, Decimal]:
        return (0, Decimal(0)) if x["value"] is None else (1, x["value"])

    if sort == "label" or sort == "time":
        rows.sort(key=lambda x: x["label"].lower())
    else:
        rows.sort(key=lambda x: x["label"].lower())  # ties by label, as the browser does
        rows.sort(key=by_value, reverse=(sort == "value-desc"))
    if q.get("limit") is not None:
        rows = rows[: q["limit"]]

    all_values = [measure.numbers[r] for r in used_rows if measure is not None and measure.numbers is not None and measure.numbers[r] is not None] if needs_value else []
    all_keys = {k[0] for r in used_rows if measure is not None and (k := _value_key(measure, r))}
    overall = _reduce(agg, all_values, len(used_rows), all_keys, scale)
    ranged = sum(1 for r in used_rows if needs_value and measure is not None and measure.ranged and measure.ranged[r])
    value_type = measure.kind if (measure is not None and needs_value and measure.numeric) else "number"
    value_name = AGG_LABEL[agg] if measure is None or not needs_value else f"{AGG_LABEL[agg]} of {measure.label}"
    return {
        "columns": [
            {"name": group.label if group else "All rows", "type": "text"},
            {"name": value_name, "type": value_type},
            {"name": "Rows", "type": "number"},
        ],
        "rows": [[x["label"], json_number(x["value"]), x["count"]] for x in rows],
        "overall": json_number(overall),
        "matched": len(matched),
        "used": len(used_rows),
        "ranged": ranged,
        "excluded": excluded[:20],
        "excluded_count": len(excluded),
        "blank": blank,
        "unit": measure.unit if measure is not None and needs_value else "",
    }


def describe(t: Typed, q: dict[str, Any], result: dict[str, Any]) -> str:
    """One plain sentence for what was calculated, so the answer can be checked."""
    agg = q["agg"]
    measure = t.columns[q["measure"]] if q.get("measure") is not None else None
    group = t.columns[q["groupBy"]] if q.get("groupBy") is not None else None
    what = {
        "count": "the number of rows", "distinct": f"the number of different {measure.label.lower()} values" if measure else "the number of different values",
        "sum": f"the total of {measure.label}" if measure else "the total", "avg": f"the average {measure.label.lower()}" if measure else "the average",
        "min": f"the lowest {measure.label.lower()}" if measure else "the lowest", "max": f"the highest {measure.label.lower()}" if measure else "the highest",
        "median": f"the median {measure.label.lower()}" if measure else "the median",
    }[agg]
    text = what[:1].upper() + what[1:]
    if group is not None:
        text += f", for each {group.label.lower()}"
        if q.get("limit"):
            text += f" ({'top' if (q.get('sort') or 'value-desc') == 'value-desc' else 'bottom'} {q['limit']})"
    text += f", over {result['used']} of {result['matched']} matching rows"
    if q.get("filters"):
        text += f" ({len(q['filters'])} filter{'s' if len(q['filters']) != 1 else ''})"
    if result.get("excluded_count"):
        text += f". {result['excluded_count']} cell(s) that are not numbers were left out"
    return text + "."
