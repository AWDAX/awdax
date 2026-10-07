"""
A scraped table read the way the app's browser code reads it, so a question answered on the server gives the same
number the dashboard would. Cells are strings ("₹12.5 lakh", "1,44,879", "(1,200)", "18.4%", "450 km", "₹11 – ₹26 Lakh");
this reads them into exact decimals and says what it read. A missing value ("N/A", "—") is never read as 0, and a range of
one measured quantity counts as its lowest value. Mirrors Frontend/src/analytics/parse.ts and profile.ts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import Any

MISSING = frozenset({
    "", "-", "--", "—", "–", "_", "?", "n/a", "na", "n.a.", "nan", "null", "none", "nil", "not found",
    "not available", "unknown", "tbd", "tba", "not disclosed", "undisclosed", "#n/a", "nd",
})

_CURRENCIES = [
    (re.compile(r"₹|\brs\.?|\binr\b", re.I), "INR"),
    (re.compile(r"us\$|\busd\b|\$", re.I), "USD"),
    (re.compile(r"€|\beur\b", re.I), "EUR"),
    (re.compile(r"£|\bgbp\b", re.I), "GBP"),
]
_SCALES = [
    (re.compile(r"^(crores?|cr)\.?$", re.I), 7, "crore"),
    (re.compile(r"^(lakhs?|lacs?|lakh|l)\.?$", re.I), 5, "lakh"),
    (re.compile(r"^(billions?|bn|b)\.?$", re.I), 9, "billion"),
    (re.compile(r"^(millions?|mn|mil|m)\.?$", re.I), 6, "million"),
    (re.compile(r"^(thousands?|k)\.?$", re.I), 3, "thousand"),
]
_APPROX = re.compile(r"^(~|≈|approx\.?|about|around|circa|ca\.)\s*", re.I)
_GROUPED = re.compile(r"^(\d{1,3}(?:,\d{2,3})+|\d{1,3}(?:[   ]\d{3})+|\d+)(\.\d+)?$")
_UNIT = re.compile(r"^[a-z][a-z0-9 ./²³-]{0,15}$", re.I)
_URL = re.compile(r"^(https?://|www\.)[^\s]+$", re.I)
_ID_NAME = re.compile(r"(^|\b|_)(id|no|sr|s\.?no|serial|rank|index|#)(\b|_|$)", re.I)
_CODE = re.compile(r"^\d{1,2}[a-z]{1,4}$", re.I)
_CATEGORY_NAME = re.compile(r"segment|type|class|category|variant|grade|tier|size|model|code", re.I)
_MEASURE_NAME = re.compile(
    r"price|cost|amount|revenue|sales|range|battery|power|speed|capacity|score|count|qty|quantity|value|volume|percentage|percent|"
    r"charging.*time|duration",
    re.I,
)

AVG_EXTRA = 2  # an average shows two more decimals than its source


@dataclass(frozen=True)
class Num:
    value: Decimal
    currency: str | None = None
    percent: bool = False
    suffix: str | None = None
    scale_word: str | None = None
    ranged: bool = False


def is_missing(text: str) -> bool:
    return " ".join(str(text).strip().lower().split()) in MISSING


def is_url(text: str) -> bool:
    return bool(_URL.match(str(text).strip()))


def _digits(body: str) -> Decimal | None:
    m = _GROUPED.match(body)
    if not m:
        bare = re.fullmatch(r"\.(\d+)", body)
        return Decimal("0." + bare.group(1)) if bare else None
    whole = m.group(1)
    if "," in whole and len(whole.split(",")[-1]) != 3:
        return None
    return Decimal(re.sub(r"[,   ]", "", whole) + (m.group(2) or ""))


def _read_one(text: str) -> Num | None:
    s = text.strip()
    approx = _APPROX.match(s)
    if approx:
        s = s[approx.end():]
    negative = False
    paren = re.fullmatch(r"\((.*)\)", s)
    if paren:
        negative, s = True, paren.group(1).strip()
    currency = None
    for pattern, code in _CURRENCIES:
        if pattern.search(s):
            currency = code
            s = pattern.sub(" ", s, count=1).strip()
            break
    if re.match(r"^[-−]", s):
        negative, s = not negative, s[1:].strip()
    elif s.startswith("+"):
        s = s[1:].strip()
    percent = False
    if s.endswith("%"):
        percent, s = True, s[:-1].strip()

    m = re.match(r"^([\d.,\s  ]*\d)\s*(.*)$", s) or re.match(r"^(\.\d+)\s*(.*)$", s)
    if not m:
        return None
    value = _digits(m.group(1).strip())
    if value is None:
        return None
    rest = re.sub(r"^[/]-$", "", m.group(2).strip())
    if rest.endswith("%") and not percent:
        percent, rest = True, rest[:-1].strip()
    parts = rest.split()
    scale_word = None
    if parts:
        for pattern, power, name in _SCALES:
            if pattern.match(parts[0]):
                value = value.scaleb(power)
                scale_word, rest = name, " ".join(parts[1:])
                break
    suffix = None
    if rest:
        if not _UNIT.match(rest) or re.search(r"\d{2,}", rest):
            return None
        suffix = rest.lower().rstrip(".")
    return Num(-value if negative else value, currency, percent, suffix, scale_word)


def _read_range(s: str) -> Num | None:
    if re.match(r"^[-−+(]", s):
        return None
    m = re.match(r"^(.+?)\s*(?:[-–—]|\bto\b)\s*(.+)$", s, re.I)
    if not m or re.search(r"\b(to|and)\b", f"{m.group(1)} {m.group(2)}", re.I):
        return None
    a, b = _read_one(m.group(1)), _read_one(m.group(2))
    if a is None or b is None:
        return None

    def unit(n: Num) -> Any:
        return n.currency or n.scale_word or n.suffix or n.percent

    if not unit(a) and not unit(b):  # bare digits: years, pages and phone numbers as often as quantities
        return None
    if a.currency and b.currency and a.currency != b.currency:
        return None
    if a.suffix and b.suffix and a.suffix != b.suffix:
        return None
    if (a.percent or b.percent) and (a.currency or b.currency or a.suffix or b.suffix):
        return None
    if any(u and re.search(r"\d", u) for u in (a.suffix, b.suffix)):
        return None
    low, high = a.value, b.value
    power = {name: p for _, p, name in _SCALES}
    if a.scale_word and not b.scale_word:
        high = high.scaleb(power[a.scale_word])
    elif b.scale_word and not a.scale_word:
        low = low.scaleb(power[b.scale_word])
    if low > high:
        return None
    return Num(low, a.currency or b.currency, a.percent or b.percent, a.suffix or b.suffix, a.scale_word or b.scale_word, True)


def parse_number(value: Any) -> Num | None:
    """One cell as a number, or None when it is missing or not a number."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return Num(Decimal(str(value))) if math.isfinite(value) else None
    s = re.sub(r"\s*[*†‡]+$", "", str(value).strip())  # a footnote mark at the very end is not part of the number
    if is_missing(s):
        return None
    ranged = _read_range(s)
    if ranged:
        return ranged
    if re.search(r"\b(to|and)\b|\d\s*[-–—]\s*\d", s, re.I):
        return None
    return _read_one(s)


def group_key(label: str) -> str:
    return " ".join(str(label).split()).lower()


def site_of(url: str) -> str:
    m = re.match(r"^(?:[a-z][a-z0-9+.-]*://)?(?:www\.)?([^/?#:\s]+)", url.strip(), re.I)
    return (m.group(1) if m else url).lower()


def humanize(name: str) -> str:
    text = re.sub(r"[_\s]+", " ", name).strip()
    return text[:1].upper() + text[1:] if text else name


@dataclass
class Column:
    index: int
    name: str
    label: str
    kind: str  # number | money | percent | category | url | text | empty
    labels: list[str]
    numbers: list[Decimal | None] | None = None
    excluded: dict[int, str] = field(default_factory=dict)  # row -> why this cell was left out of the numbers
    ranged: list[bool] | None = None
    scale: int = 0
    currency: str | None = None
    percent: bool = False
    suffix: str | None = None
    id_like: bool = False
    distinct: int = 0

    @property
    def numeric(self) -> bool:
        return self.kind in ("number", "money", "percent")

    @property
    def unit(self) -> str:
        return self.currency or ("%" if self.percent else (self.suffix or ""))


@dataclass
class Typed:
    columns: list[Column]
    row_count: int
    raw: list[list[str]]


def _decimals(d: Decimal) -> int:
    exp = d.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def _profile_column(index: int, name: str, label: str, cells: list[str]) -> Column:
    present = [(row, c) for row, c in enumerate(cells) if c != "" and not is_missing(c)]
    filled = len(present)
    distinct = len({group_key(c) for _, c in present})
    base = {"index": index, "name": name, "label": label, "labels": cells, "distinct": distinct}
    if filled == 0:
        return Column(kind="empty", **base)
    need = max(1, math.ceil(filled * 0.8))
    if sum(1 for _, c in present if is_url(c)) >= need:
        return Column(kind="url", **base)

    nums = [(row, c, parse_number(c)) for row, c in present]
    ok = [x for x in nums if x[2] is not None]
    codes = sum(1 for _, c in present if _CODE.match(c.strip()))
    code_like = (codes >= need and distinct <= 12 and distinct <= filled * 0.5) or (
        _CATEGORY_NAME.search(name) and distinct <= 20 and distinct <= filled * 0.5
    )
    named_measure = _MEASURE_NAME.search(name) and len(ok) >= 2 and len(ok) >= math.ceil(filled * 0.2)
    if (len(ok) >= need or named_measure) and not code_like:
        parsed = [x[2] for x in ok]
        currencies = [p.currency for p in parsed if p.currency]
        currency = max(set(currencies), key=currencies.count) if currencies else None
        suffixes = [p.suffix for p in parsed if p.suffix]
        suffix = max(set(suffixes), key=suffixes.count) if suffixes else None
        percent = sum(1 for p in parsed if p.percent) * 2 > len(parsed)
        numbers: list[Decimal | None] = [None] * len(cells)
        ranged = [False] * len(cells)
        excluded: dict[int, str] = {}
        scale = 0
        for row, c, p in nums:
            if p is None:
                excluded[row] = "not a number"
            elif p.currency and currency and p.currency != currency:
                excluded[row] = f"in {p.currency}, the column is in {currency}"
            elif p.suffix and suffix and p.suffix != suffix:
                excluded[row] = f"in “{p.suffix}”, the column is in “{suffix}”"
            else:
                numbers[row] = p.value
                ranged[row] = p.ranged
                scale = max(scale, _decimals(p.value))
        kind = "money" if sum(1 for p in parsed if p.currency) * 2 > len(parsed) else ("percent" if percent else "number")
        ints = [n for n in numbers if n is not None]
        consecutive = len(ints) > 2 and all(n == i + 1 for i, n in enumerate(ints))
        return Column(
            kind=kind, numbers=numbers, excluded=excluded, ranged=ranged if any(ranged) else None, scale=scale,
            currency=currency if kind == "money" else None, percent=kind == "percent", suffix=suffix,
            id_like=kind == "number" and bool(_ID_NAME.search(name) or consecutive), **base,
        )
    avg_len = sum(len(c) for _, c in present) / filled
    category = distinct >= 1 and avg_len <= 48 and (distinct <= 12 or distinct <= math.ceil(filled * 0.6))
    return Column(kind="category" if category else "text", **base)


def profile_table(columns: list[str], rows: list[list[Any]], labels: list[str] | None = None) -> Typed:
    """Read a table (column keys and rows of cells) into typed columns."""
    raw = [["" if c is None else str(c).strip() for c in (list(r) + [""] * len(columns))[: len(columns)]] for r in rows]
    cols = [
        _profile_column(i, key, (labels[i] if labels and i < len(labels) and labels[i] else humanize(key)), [r[i] for r in raw])
        for i, key in enumerate(columns)
    ]
    return Typed(cols, len(raw), raw)


def _ask_key(name: str, used: set[str], index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or f"col{index}"
    key = base
    n = 2
    while key in used:
        key, n = f"{base}_{n}", n + 1
    used.add(key)
    return key


def ask_payload(typed: Typed) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The table as the question planner reads it: readable columns, and rows of exact numbers (as floats) or text."""
    used: set[str] = set()
    cols = []
    for c in typed.columns:
        if c.kind == "empty":
            continue
        cols.append({"index": c.index, "key": _ask_key(c.name, used, c.index), "label": c.label, "kind": c.kind, "unit": c.unit})
    rows = []
    for r in range(typed.row_count):
        row: dict[str, Any] = {}
        for a in cols:
            c = typed.columns[a["index"]]
            if c.numbers is not None:
                row[a["key"]] = float(c.numbers[r]) if c.numbers[r] is not None else None
            else:
                row[a["key"]] = c.labels[r] or None
        rows.append(row)
    return cols, rows


def mean(values: list[Decimal], scale: int) -> Decimal | None:
    """The mean, rounded half to even at `scale` decimals (as the browser does)."""
    if not values:
        return None
    with localcontext() as ctx:
        ctx.prec = 80
        return (sum(values, Decimal(0)) / Decimal(len(values))).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_EVEN)


def median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    with localcontext() as ctx:
        ctx.prec = 80
        pair = s[mid - 1] + s[mid]
        return (pair / Decimal(2)).quantize(Decimal(1).scaleb(-(max(_decimals(pair), 0) + 1)), rounding=ROUND_HALF_EVEN)
