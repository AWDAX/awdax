"""
Plain questions answered without the AI: "how many rows", "average rating", "total reviews by category", "top 5 by reviews".

A question becomes the same checked plan the AI would produce (ask_data.check_query), which the engine then runs exactly.
It answers only what it can read with no doubt: every word must be accounted for and every column named must be found
once. A filter ("in Noida", "with a website"), a comparison, a calculation, an unknown word or a column that could be two
returns None and goes to the AI. It is faster, costs nothing, and works when the model is down.
"""

from __future__ import annotations

import re
from typing import Any

Plan = dict[str, Any]

# Words that carry no meaning for these questions.
_FILLER = frozenset({
    "what", "whats", "which", "is", "are", "was", "were", "the", "a", "an", "of", "please", "can", "could", "you", "tell", "show",
    "give", "me", "us", "calculate", "compute", "find", "get", "do", "does", "did", "there", "overall", "all", "table", "data",
    "dataset", "in", "for",
})
_CONNECT = {"by", "per", "across", "each"}
_NUMERIC = ("number", "money", "percent")
_AGG = {
    "average": "avg", "avg": "avg", "mean": "avg", "median": "median", "total": "sum", "sum": "sum",
    "highest": "max", "maximum": "max", "max": "max", "largest": "max", "biggest": "max",
    "lowest": "min", "minimum": "min", "min": "min", "smallest": "min",
}
_COUNT_NOUNS = frozenset({
    "row", "record", "entry", "item", "result", "place", "business", "lead", "listing", "company", "model", "shop", "clinic",
    "restaurant", "cafe", "store", "gazette", "notification", "source",
})
_COUNT_FILLER = frozenset({"total", "have", "we", "i", "found", "collected", "scraped", "here", "now", "far", "so", "got", "many", "how", "number", "count", "exist"})


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _normalise(question: str) -> list[str]:
    text = question.lower().replace("’", "'")
    text = re.sub(r"\b(?:for each|grouped by|group by|broken down by|split by|segmented by)\b", " by ", text)
    text = re.sub(r"[^a-z0-9%\s]", " ", text)
    return text.split()


def _phrases(col: dict[str, Any]) -> list[list[str]]:
    """The ways a person may name a column: its label and its key."""
    out: list[list[str]] = []
    for source in (col.get("label") or "", str(col.get("key") or "").replace("_", " ")):
        words = [_singular(w) for w in _normalise(str(source))]
        if words and words not in out:
            out.append(words)
    return out


def _find_column(tokens: list[str], cols: list[dict[str, Any]], *, numeric: bool = False) -> tuple[dict[str, Any] | None, list[str]]:
    """The one column the tokens name, and the tokens left over. (None, tokens) when there is none or it is not clear."""
    singular = [_singular(t) for t in tokens]
    hits: list[tuple[dict[str, Any], int, int]] = []
    for col in cols:
        if numeric and col["kind"] not in _NUMERIC:
            continue
        for phrase in _phrases(col):
            n = len(phrase)
            hits += [(col, i, n) for i in range(len(singular) - n + 1) if singular[i : i + n] == phrase]
    if not hits:
        return None, tokens
    longest = max(n for _, _, n in hits)
    best = [h for h in hits if h[2] == longest]
    if len({h[0]["index"] for h in best}) != 1:
        return None, tokens
    col, i, n = best[0]
    return col, tokens[:i] + tokens[i + n :]


def _name_column(cols: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The column that names a row: the first one of words (not numbers or links)."""
    return next((c for c in cols if c["kind"] in ("text", "category")), None)


def _plan(**query: Any) -> Plan:
    return {"kind": "query", "query": {k: v for k, v in query.items() if v is not None}}


def _split_by(words: list[str]) -> tuple[list[str], list[str] | None]:
    """("before", "after") around the first "by"/"per"/"across"; after is None when there is no such word."""
    for i, w in enumerate(words):
        if w in _CONNECT:
            return words[:i], words[i + 1 :]
    return words, None


def _count(words: list[str], cols: list[dict[str, Any]]) -> Plan | None:
    before, after = _split_by(words)
    leftover = [w for w in before if w not in _COUNT_FILLER and _singular(w) not in _COUNT_NOUNS]
    if leftover:
        return None
    if after is None:
        return _plan(agg="count")
    group, left = _find_column(after, cols)
    return _plan(groupBy=group["index"], agg="count") if group and not left else None


def plan(question: str, cols: list[dict[str, Any]]) -> Plan | None:
    """A plan for a plain question, or None to leave it to the AI."""
    if not question or len(question) > 200 or not cols:
        return None
    words = [w for w in _normalise(question) if w not in _FILLER]
    if not words or any(w.isdigit() for w in words[2:]) or "%" in "".join(words):
        return None

    # how many ...  /  number of ...  /  count ...
    if words[:2] == ["how", "many"] or words[:2] == ["total", "number"] or words[0] in ("number", "count"):
        return _count(words, cols)

    # top 5 by reviews  /  bottom 3 by rating
    if words[0] in ("top", "bottom", "best", "worst") and len(words) >= 3 and words[1].isdigit():
        limit = int(words[1])
        measure, left = _find_column([w for w in words[2:] if w not in _CONNECT and w != "on"], cols, numeric=True)
        name = _name_column(cols)
        if measure is None or left or name is None or not 1 <= limit <= 50:
            return None
        descending = words[0] in ("top", "best")
        # Each row is its own group; a name that repeats is ranked by its best (top) or its worst (bottom) value.
        return _plan(groupBy=name["index"], measure=measure["index"], agg="max" if descending else "min", sort="value-desc" if descending else "value-asc", limit=limit)

    # average rating  /  total reviews by category  /  highest price
    aggs = {_AGG[w] for w in words if w in _AGG}
    if len(aggs) != 1:
        return None
    agg = aggs.pop()
    rest = [w for w in words if w not in _AGG]
    before, after = _split_by(rest)
    measure, left = _find_column(before, cols, numeric=True)
    if measure is None or left:
        return None
    group = None
    if after is not None:
        group, left = _find_column(after, cols)
        if group is None or left or group["index"] == measure["index"]:
            return None
    return _plan(groupBy=group["index"] if group else None, measure=measure["index"], agg=agg, sort="value-desc" if group else None)
