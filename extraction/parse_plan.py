"""Parse extraction_query key=value blocks from step 2."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedExtractionQuery:
    method: str = "headless_dom"
    url: str = ""
    target: str = ""
    columns: list[str] = field(default_factory=list)
    pagination: str = "none"
    notes: str = ""


def parse_extraction_query(text: str, *, fallback_url: str) -> ParsedExtractionQuery:
    out = ParsedExtractionQuery(url=fallback_url)
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip().upper(), val.strip()
        if key == "METHOD":
            out.method = val.lower()
        elif key == "URL" and val:
            out.url = val
        elif key == "TARGET":
            out.target = val
        elif key == "COLUMNS" and val:
            out.columns = [c.strip() for c in val.split(",") if c.strip()]
        elif key == "PAGINATION":
            out.pagination = val
        elif key == "NOTES":
            out.notes = val
    return out
