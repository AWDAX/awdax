"""Drop junk rows from heuristic / partial extracts."""

from __future__ import annotations

import re

_PRICE_OK = re.compile(
    r"(₹|rs\.?\s*\d|\d[\d,.]*\s*(lakh|lac|cr|crore)|on-road|ex-showroom)",
    re.I,
)
_MODEL_OK = re.compile(r"[a-zA-Z]{2,}")
_JUNK_MODEL = re.compile(
    r"^(under|recommended|priced from|rs\.|₹|\d+\.\d+\s*-|\*|\.{2,})",
    re.I,
)


def is_valid_ev_row(row: dict[str, str]) -> bool:
    model = (row.get("model") or row.get("car_name") or row.get("name") or "").strip()
    price = (
        row.get("ex_showroom_price")
        or row.get("price")
        or row.get("price_range")
        or ""
    ).strip()
    if not model and not price:
        return False
    if model and _JUNK_MODEL.match(model):
        return False
    if model and not _MODEL_OK.search(model):
        return False
    if model and re.match(r"^[\d.\s\-*–]+$", model):
        return False
    if not model:
        return False
    if price and not _PRICE_OK.search(price) and not re.search(r"\d+\.\d{2}", price):
        # bare "16.19" without lakh context — only ok if model is real
        if not model or len(model) < 4:
            return False
    if model and len(model) < 3:
        return False
    if "on-road price, mumbai" in model.lower() and len(model) > 80:
        return False
    return bool(model and price)


def filter_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not is_valid_ev_row(row):
            continue
        model = (row.get("model") or row.get("car_name") or row.get("name") or "").strip()
        price = (
            row.get("ex_showroom_price") or row.get("price") or row.get("price_range") or ""
        ).strip()
        key = f"{model.lower()}|{price.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out
