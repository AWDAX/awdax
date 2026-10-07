"""
Filter junk rows (FAQ questions, article headlines, nav text). The headline/length/price rules were written for vehicle
catalogs and only apply to a vehicle topic; question-shaped, navigation and URL-only names are junk for any topic.
"""

from __future__ import annotations

import re
from typing import Any

_QUESTION_START = re.compile(
    r"^(which|what|how|why|when|where|is|are|can|do|does|did|will|should|could|would)\b",
    re.I,
)
_ARTICLE_PATTERNS = re.compile(
    r"\b(could be your|gateway to|review|vs\.|versus|compared to|launched in|coming in 20)\b",
    re.I,
)
_NAV_JUNK = frozenset(
    {
        "electric cars",
        "view all",
        "compare",
        "home",
        "read more",
        "see all",
        "show more",
        "filter",
        "sort by",
    }
)

# Real model names are rarely longer than this many words
_MAX_NAME_WORDS = 7

_VEHICLE_TOPIC = re.compile(
    r"\b(evs?|electric\s+(?:car|vehicle|scooter|bike|motorcycle)s?|cars?|bikes?|motorcycles?|scooters?|suvs?|sedans?|vehicles?|"
    r"hatchbacks?|automobiles?)\b",
    re.I,
)


def topic_is_vehicles(raw_prompt: str = "", topic: str = "") -> bool:
    """Whether the request is about cars/bikes, where the vehicle-catalog junk rules make sense."""
    return bool(_VEHICLE_TOPIC.search(f"{raw_prompt} {topic}"))


def _name_field(row: dict[str, Any], columns: list[str] | None = None) -> str:
    cols = columns or []
    for key in ("car_name", "name", "model", "model_name"):
        if row.get(key):
            return str(row[key]).strip()
    if cols and cols[0] in row:
        return str(row[cols[0]]).strip()
    return ""


def is_junk_vehicle_name(name: str, *, require_price_hint: bool = False, has_price: bool = False, vehicle: bool = True) -> bool:
    n = (name or "").strip()
    if not n or len(n) < 2:
        return True
    low = n.lower()
    if low in _NAV_JUNK:
        return True
    if n.endswith("?"):
        return True
    if not vehicle:
        # Any other topic keeps a long first column (a quote, a debate title, a headline) and a title that starts with a
        # question word ("Do not go gentle..."); only question-shaped (ending in "?"), navigation and URL-only names are junk.
        return False
    if len(n) > 140 or _QUESTION_START.search(n):
        return True
    if _ARTICLE_PATTERNS.search(n):
        return True
    # FAQ blocks on aggregator pages
    if " in india" in low and ("which " in low or "what " in low or "lowest priced" in low or "most expensive" in low):
        return True
    if "popular electric cars" in low or "upcoming electric cars" in low or "recently launched electric" in low:
        return True
    if "latest electric cars" in low and "which" in low:
        return True

    words = n.split()
    if len(words) > _MAX_NAME_WORDS:
        # Long sentence-like titles without price are not model names
        if not has_price and not re.search(r"\bev\b", low, re.I):
            return True
        if len(words) > 12:
            return True

    if require_price_hint and not has_price:
        # Question-shaped or generic list titles without a price
        if any(w in low for w in ("cheapest", "economical", "expensive", "popular", "upcoming", "latest")):
            return True

    return False


def is_valid_vehicle_row(
    row: dict[str, Any],
    columns: list[str] | None = None,
    *,
    catalog_with_prices: bool = False,
    vehicle: bool = True,
) -> bool:
    if not isinstance(row, dict):
        return False
    name = _name_field(row, columns)
    price = str(row.get("price") or row.get("price_inr") or row.get("Price (INR)") or "").strip()
    has_price = bool(price) and bool(re.search(r"[\d₹]|lakh|cr\b|rs\.?", price, re.I))
    if is_junk_vehicle_name(name, require_price_hint=catalog_with_prices, has_price=has_price, vehicle=vehicle):
        return False
    # Single-field rows that are only URL-like
    if name.startswith("http"):
        return False
    return True


def filter_vehicle_rows(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    *,
    catalog_with_prices: bool = False,
    vehicle: bool = True,
) -> list[dict[str, Any]]:
    return [r for r in rows if is_valid_vehicle_row(r, columns, catalog_with_prices=catalog_with_prices, vehicle=vehicle)]


def intent_expects_priced_catalog(raw_prompt: str, topic: str = "") -> bool:
    blob = f"{raw_prompt} {topic}".lower()
    return "price" in blob and ("all " in blob or "list" in blob or "ev" in blob or "electric" in blob)
