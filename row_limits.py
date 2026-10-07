"""
Limits the user put on the rows, enforced on every row before it is stored.

"Debates between 2010 to 2025" used to be a wish passed to the model, which sometimes returned 2026 rows anyway. Here the
period is read from the request itself and each row's date is checked: a row dated outside it is dropped. A row with no
readable date is kept (nothing proves it is outside), and the count of dropped rows is reported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_YEAR = r"(1[89]\d\d|20\d\d|21\d\d)"


@dataclass(frozen=True)
class Period:
    start: date | None
    end: date | None

    def contains(self, d: date) -> bool:
        return (self.start is None or d >= self.start) and (self.end is None or d <= self.end)

    def label(self) -> str:
        a = self.start.isoformat() if self.start else "…"
        b = self.end.isoformat() if self.end else "…"
        return f"{a} to {b}"


def period_from_text(text: str, *, today: date | None = None) -> Period | None:
    """The period a request limits its rows to, from its own words. None when it names none.

    Understood: "between 2010 and 2025", "from 2010 to 2025", "2010-2025", "2010 to 2025", "since 2015", "after 2015",
    "before 2020", "until 2020", "up to 2020", "in 2023", "during 2023", "last 5 years", "past 3 years"."""
    t = " ".join((text or "").lower().split())
    if not t:
        return None
    today = today or date.today()
    m = re.search(rf"(?:between|from)?\s*{_YEAR}\s*(?:and|to|till|until|through|thru|-|–|—)\s*{_YEAR}\b", t)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return Period(date(a, 1, 1), date(b, 12, 31))
    m = re.search(r"\b(?:last|past|previous)\s+(\d{1,3})\s+years?\b", t)
    if m:
        return Period(date(today.year - int(m.group(1)), today.month, min(today.day, 28)), today)
    m = re.search(rf"\b(since|from|after|starting(?: in| from)?)\s+{_YEAR}\b", t)
    if m:
        y = int(m.group(2)) + (1 if m.group(1) == "after" else 0)
        return Period(date(y, 1, 1), None)
    m = re.search(rf"\b(before|until|till|up to|upto|prior to)\s+{_YEAR}\b", t)
    if m:
        y = int(m.group(2)) - (1 if m.group(1) in ("before", "prior to") else 0)
        return Period(None, date(y, 12, 31))
    m = re.search(rf"\b(?:in|during|for the year|of the year)\s+{_YEAR}\b", t)
    if m:
        y = int(m.group(1))
        return Period(date(y, 1, 1), date(y, 12, 31))
    return None


def parse_date(value: Any) -> date | None:
    """A date (or a year, as its 1 January) from the ways pages write them: 2025-02-04, 04/02/2025, 4-Feb-2025,
    February 4, 2025, 4 Feb 2025, Feb 2025, 2025, "2015 [60]". Day-first when a numeric date is ambiguous."""
    s = str(value or "").strip()
    if not s:
        return None
    s = re.sub(r"\[[^\]]*\]", " ", s).strip()  # footnote marks
    try:
        m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b", s)
        if m:
            a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            day, month = (a, b) if a > 12 or b <= 12 else (b, a)
            return date(y, month, day)
        m = re.match(r"^(\d{1,2})(?:st|nd|rd|th)?[-\s/.]+([a-z]{3,9})\.?[-\s/.,]+(\d{2,4})\b", s, re.I)
        if m and m.group(2)[:3].lower() in _MONTHS:
            y = int(m.group(3))
            return date(y + 2000 if y < 100 else y, _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        m = re.match(r"^([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", s, re.I)
        if m and m.group(1)[:3].lower() in _MONTHS:
            return date(int(m.group(3)), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
        m = re.match(r"^([a-z]{3,9})\.?,?\s+(\d{4})\b", s, re.I)
        if m and m.group(1)[:3].lower() in _MONTHS:
            return date(int(m.group(2)), _MONTHS[m.group(1)[:3].lower()], 1)
        m = re.fullmatch(rf"{_YEAR}(?:\s*[-–/]\s*\d{{2,4}})?", s)  # 2015, or a span such as 2015-16 (its first year)
        if m:
            return date(int(m.group(1)), 1, 1)
    except ValueError:
        return None
    return None


_DATE_WORDS = re.compile(r"date|year|time|period|day|month|when|published|issued|held|established|founded|launched|on$", re.I)


def date_column(rows: list[dict[str, Any]], columns: Iterable[str]) -> str | None:
    """The column that dates each row: a date-named column whose values mostly read as dates, else any such column."""
    cols = [c for c in columns if c and not str(c).startswith("_")]
    sample = [r for r in rows if isinstance(r, dict)][:200]
    if not sample:
        return None

    def share(col: str) -> float:
        vals = [r.get(col) for r in sample if str(r.get(col) or "").strip()]
        return sum(1 for v in vals if parse_date(v)) / len(vals) if vals else 0.0

    named = [(share(c), c) for c in cols if _DATE_WORDS.search(str(c))]
    best = max(named, default=(0.0, None))
    if best[0] >= 0.5:
        return best[1]
    any_col = max(((share(c), c) for c in cols if c not in ("source_url", "url")), default=(0.0, None))
    return any_col[1] if any_col[0] >= 0.8 else None


def apply_period(rows: list[dict[str, Any]], columns: Iterable[str], period: Period | None) -> tuple[list[dict[str, Any]], int]:
    """(rows inside the period, number dropped). Rows without a readable date are kept."""
    if period is None or not rows:
        return rows, 0
    col = date_column(rows, columns)
    if not col:
        return rows, 0
    kept: list[dict[str, Any]] = []
    for r in rows:
        d = parse_date(r.get(col))
        if d is None or period.contains(d):
            kept.append(r)
    return kept, len(rows) - len(kept)


def period_for_intent(intent: Any) -> Period | None:
    """The period of a ScrapeIntent: from the user's words, then its constraints and freshness."""
    if intent is None:
        return None
    for text in [getattr(intent, "raw_prompt", ""), *(getattr(intent, "constraints", None) or []), getattr(intent, "freshness", "")]:
        p = period_from_text(str(text or ""))
        if p:
            return p
    return None
