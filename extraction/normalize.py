"""Normalize row keys to a stable EV listing schema."""

from __future__ import annotations

import re

_STD = ("brand", "model", "ex_showroom_price", "range", "battery_capacity", "power")

_KEY_MAP = {
    "car_name": "model",
    "name": "model",
    "model_name": "model",
    "price": "ex_showroom_price",
    "price_range": "ex_showroom_price",
    "price_inr": "ex_showroom_price",
    "range_km": "range",
    "battery": "battery_capacity",
}


def normalize_row(row: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {k: "" for k in _STD}
    for k, v in row.items():
        if not v:
            continue
        key = _KEY_MAP.get(k.lower(), k.lower())
        if key in out and not out[key]:
            out[key] = str(v).strip()
        elif key not in out and key in _STD:
            out[key] = str(v).strip()
    # Clean price display
    p = out["ex_showroom_price"]
    if p and not re.search(r"lakh|lac|₹|rs", p, re.I) and re.match(r"^[\d.]+$", p):
        out["ex_showroom_price"] = f"₹ {p} Lakh"
    return out


def normalize_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [normalize_row(r) for r in rows]
