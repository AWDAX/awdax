"""
Extract structured rows from page HTML (tables, JSON-LD, text) via digest + Gemini.
"""

from __future__ import annotations

import json
import re
from typing import Any

from reasoning import ScrapeIntent, gemini_json


def _strip_html_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def _strip_scripts_styles(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html).strip()


def build_page_digest(html: str, *, max_text: int = 55_000) -> dict[str, Any]:
    json_ld: list[Any] = []
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            json_ld.append(json.loads(block.strip()[:8000]))
        except Exception:
            json_ld.append(block.strip()[:2000])
        if len(json_ld) >= 4:
            break

    next_m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.I | re.S)
    next_snip = (next_m.group(1)[:80000] if next_m else "")

    from scraper import extract_tables_from_html

    tables = extract_tables_from_html(html)
    table_preview = []
    for t in tables[:3]:
        table_preview.append(
            {
                "headers": (t.get("headers") or [])[:20],
                "sample_rows": (t.get("rows") or [])[:5],
            }
        )

    text = _strip_html_tags(_strip_scripts_styles(html))[:max_text]

    return {
        "json_ld": json_ld,
        "next_data_snippet": next_snip,
        "tables": table_preview,
        "visible_text_sample": text,
    }


def rows_from_tables(html: str, columns: list[str]) -> list[dict[str, Any]]:
    """Map largest HTML table to row dicts (heuristic)."""
    from scraper import extract_tables_from_html

    tables = extract_tables_from_html(html)
    if not tables:
        return []
    best = max(tables, key=lambda t: len(t.get("rows") or []))
    headers = best.get("headers") or []
    rows_raw = best.get("rows") or []
    if not rows_raw:
        return []
    if not headers:
        width = max(len(r) for r in rows_raw)
        headers = [f"col_{i}" for i in range(width)]

    out: list[dict[str, Any]] = []
    for i, values in enumerate(rows_raw):
        row = {c: "" for c in columns}
        for j, h in enumerate(headers):
            if j >= len(values):
                break
            val = values[j]
            hl = h.lower()
            for col in columns:
                if col.replace("_", " ") in hl or hl in col.replace("_", " "):
                    row[col] = val
                    break
        if columns:
            if not row.get(columns[0]) and values:
                row[columns[0]] = values[0]
            if len(columns) > 1 and not row.get(columns[1]) and len(values) > 1:
                row[columns[1]] = values[1]
        if any(v for v in row.values()):
            row["_row_key"] = "|".join(values[:4])[:120]
            out.append(row)
    return out


def ai_extract_rows_from_html(
    html: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
) -> list[dict[str, Any]]:
    if len(html) < 400:
        return []
    digest = build_page_digest(html)
    prompt = f"""Extract listing data from this web page digest into a JSON object.

User goal: {intent.raw_prompt or intent.topic}
Page URL: {page_url}

Output columns (use exactly these keys on every row): {json.dumps(columns)}

Rules:
- Extract ONLY electric vehicle MODEL nameplates (e.g. Tata Nexon EV, MG Comet EV).
- Do NOT include FAQ questions, blog titles, or sentences (no "Which are the...", "Why the 2026...", text ending with ?).
- Use empty string for missing fields.
- Do not invent models not present in the digest.
- Prefer prices/ranges from visible text or JSON-LD.

Digest:
{json.dumps(digest, default=str)[:120000]}

Return JSON: {{ "rows": [ {{ {", ".join(columns)} }} ] }}"""

    try:
        data = gemini_json(prompt)
        if isinstance(data, dict) and isinstance(data.get("rows"), list):
            out: list[dict[str, Any]] = []
            for item in data["rows"]:
                if not isinstance(item, dict):
                    continue
                row = {c: str(item.get(c) or "").strip() for c in columns}
                if any(row.values()):
                    out.append(row)
            return out
    except Exception:
        pass
    return []


def extract_rows_from_page_html(
    html: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
    column_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    from gemini_scrape import gemini_extract_rows_from_page

    return gemini_extract_rows_from_page(
        html,
        intent,
        columns,
        page_url=page_url,
        column_labels=column_labels,
    )
