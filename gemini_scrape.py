"""
Gemini-only page → table row extraction for universal scrape runs.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from listing_extract import _strip_html_tags, extract_tables_from_html
from reasoning import ScrapeIntent, gemini_json

logger = logging.getLogger(__name__)


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


def build_gemini_page_context(html: str, *, page_url: str = "") -> dict[str, Any]:
    """Rich context for Gemini (JSON blobs + visible text)."""
    ctx = build_page_digest(html, max_text=int(os.getenv("GEMINI_SCRAPE_MAX_TEXT", "70000")))
    ctx["page_url"] = page_url

    next_full = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
    if next_full:
        cap = int(os.getenv("GEMINI_SCRAPE_NEXT_DATA_CHARS", "200000"))
        ctx["next_data"] = next_full.group(1)[:cap]

    return ctx


def gemini_extract_rows_from_page(
    html: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
    source_name: str = "",
    column_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Primary scrape extractor: Gemini reads page context and returns rows."""
    if len(html) < 400 or not columns:
        return []

    labels = column_labels or columns
    label_hint = json.dumps(dict(zip(columns, labels)), ensure_ascii=False)

    ctx = build_gemini_page_context(html, page_url=page_url)
    ctx_json = json.dumps(ctx, default=str)
    max_ctx = int(os.getenv("GEMINI_SCRAPE_CONTEXT_CHARS", "180000"))
    if len(ctx_json) > max_ctx:
        ctx_json = ctx_json[:max_ctx]

    prompt = f"""You are extracting structured data from a web page for scraping.

User goal: {intent.raw_prompt or intent.topic}
Page URL: {page_url}
Source: {source_name or page_url}

Output table columns (keys → meaning):
{label_hint}

Rules:
- Return ONLY real data rows that match the user goal (e.g. electric car model nameplates with prices when asked).
- Do NOT include FAQ questions, SEO headings, or blog titles (no "Which are the...", no text ending with ?).
- Use empty string for missing fields; do not guess prices.
- Extract as many valid items as appear in the page context (full listing, not just featured).
- Use exactly these keys on every row: {json.dumps(columns)}

Page context (JSON):
{ctx_json}

Return JSON only: {{ "rows": [ {{ ... }} ] }}"""

    try:
        data = gemini_json(prompt, temperature=float(os.getenv("GEMINI_SCRAPE_TEMPERATURE", "0.15")))
    except Exception as e:
        logger.warning("Gemini scrape extract failed: %s", e)
        return []

    if isinstance(data, list):
        data = {"rows": data}
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list):
        return []

    out: list[dict[str, Any]] = []
    for item in data["rows"]:
        if not isinstance(item, dict):
            continue
        row = {c: str(item.get(c) or item.get(c.replace("_", " ")) or "").strip() for c in columns}
        if any(v for v in row.values()):
            out.append(row)
    return out
