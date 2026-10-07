"""
Model-based page → table row extraction for universal scrape runs.

The page is shown to the model as structured context: JSON-LD and Next.js data when present, every sizeable HTML table as
compact rows (one row a line, so rows stay rows), and the visible text. A long table is read in chunks, so a 300-row list is
not cut off at the model's output limit.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from listing_extract import _strip_html_tags, extract_tables_from_html, table_to_text
from reasoning import ScrapeIntent, gemini_json

logger = logging.getLogger(__name__)

MAX_TABLES = 6


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def _strip_scripts_styles(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html).strip()


_TITLED_LINK = re.compile(r"(<a\b[^>]*\btitle\s*=\s*[\"']([^\"']+)[\"'][^>]*>)([^<]*)(</a>)", re.I)


def restore_truncated_text(html: str) -> str:
    """A link shown as "A Light in the ..." keeps its full text in its title attribute (cards on shop and catalogue sites).
    Put the full text back, or the model returns the cut-off title."""

    def fix(m: re.Match[str]) -> str:
        shown, full = m.group(3).strip(), m.group(2).strip()
        stem = shown.rstrip(".\u2026 ").rstrip()
        if shown.endswith(("...", "\u2026")) and stem and full.lower().startswith(stem.lower()) and len(full) > len(stem):
            return f"{m.group(1)}{full}{m.group(4)}"
        return m.group(0)

    return _TITLED_LINK.sub(fix, html)


def build_page_digest(html: str, *, max_text: int = 55_000, max_table_chars: int = 60_000) -> dict[str, Any]:
    html = restore_truncated_text(html)
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

    # The biggest tables, as rows. Layout tables with one row are left to the page text.
    rendered: list[dict[str, Any]] = []
    budget = max_table_chars
    sized = sorted((t for t in extract_tables_from_html(html) if len(t["rows"]) >= 2), key=lambda t: len(t["rows"]), reverse=True)
    for table in sized[:MAX_TABLES]:
        text, shown = table_to_text(table, max_chars=max(budget, 0))
        if not shown:
            break
        rendered.append({"columns": table["headers"], "rows_shown": shown, "rows_total": len(table["rows"]), "rows": text})
        budget -= len(text)
        if budget <= 0:
            break

    # The tables are in the context already; the page text is for what is outside them, so it can be shorter.
    text = _strip_html_tags(_strip_scripts_styles(html))[: min(max_text, 20_000) if rendered else max_text]
    return {"json_ld": json_ld, "next_data_snippet": next_snip, "tables": rendered, "visible_text_sample": text}


def build_gemini_page_context(html: str, *, page_url: str = "") -> dict[str, Any]:
    """Rich context for the model (JSON blobs, tables as rows, visible text)."""
    ctx = build_page_digest(html, max_text=_env_int("GEMINI_SCRAPE_MAX_TEXT", 70000))
    ctx["page_url"] = page_url

    next_full = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    )
    if next_full:
        ctx["next_data"] = next_full.group(1)[: _env_int("GEMINI_SCRAPE_NEXT_DATA_CHARS", 200000)]

    return ctx


def _prompt(intent: ScrapeIntent, columns: list[str], label_hint: str, *, page_url: str, source_name: str, context: str, note: str = "") -> str:
    return f"""You are extracting structured data from a web page for scraping.

User goal: {intent.raw_prompt or intent.topic}
Page URL: {page_url}
Source: {source_name or page_url}
{note}
Output table columns (keys → meaning):
{label_hint}

Rules:
- Return ONLY real data rows that match the user goal: one row per real item (a product, place, person, listing, record), as it appears on the page.
- Do NOT include FAQ questions, SEO headings, navigation, ads, or blog titles (no "Which are the...", no text ending with ?).
- Copy values as written on the page (keep currency symbols, units, ranges); never calculate or infer one.
- Use empty string for missing fields; do not guess prices.
- If the user goal sets limits (a period such as "2010 to 2025", a place, a category), return only rows inside them.
- Extract as many valid items as appear in the page context (full listing, not just featured).
- Use exactly these keys on every row: {json.dumps(columns)}

Page context (JSON):
{context}

Return JSON only: {{ "rows": [ {{ ... }} ] }}"""


def _rows_from(data: Any, columns: list[str]) -> list[dict[str, Any]]:
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


def _extract_big_table(
    table: dict[str, Any], intent: ScrapeIntent, columns: list[str], label_hint: str, *, page_url: str, source_name: str
) -> list[dict[str, Any]]:
    """A table with more rows than one answer can hold, read part by part. A failed part loses only its own rows."""
    size = _env_int("GEMINI_SCRAPE_CHUNK_ROWS", 60)
    chunks = [table["rows"][i : i + size] for i in range(0, len(table["rows"]), size)][: _env_int("GEMINI_SCRAPE_MAX_CHUNKS", 8)]
    out: list[dict[str, Any]] = []
    for n, chunk in enumerate(chunks, start=1):
        text, _ = table_to_text({"headers": table["headers"], "rows": chunk}, max_chars=60_000)
        ctx = {"page_url": page_url, "table": {"columns": table["headers"], "rows": text, "rows_total_in_table": len(table["rows"])}}
        note = f"This is part {n} of {len(chunks)} of one long table: return a row for every data row below that fits the goal.\n"
        prompt = _prompt(intent, columns, label_hint, page_url=page_url, source_name=source_name, context=json.dumps(ctx, default=str), note=note)
        try:
            out += _rows_from(gemini_json(prompt, temperature=float(os.getenv("GEMINI_SCRAPE_TEMPERATURE", "0.15"))), columns)
        except Exception as e:
            logger.warning("Table part %d of %d could not be read: %s", n, len(chunks), e)
    return out


def gemini_extract_rows_from_tree(
    tree: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
    source_name: str = "",
    column_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """The model reads the page's accessibility tree (ax_reader.tree_text) and returns its rows. A long tree is read in parts."""
    if len(tree) < 100 or not columns:
        return []
    labels = column_labels or columns
    label_hint = json.dumps(dict(zip(columns, labels)), ensure_ascii=False)
    size = _env_int("AX_CHUNK_CHARS", 60_000)
    lines, parts, current, used = tree.splitlines(), [], [], 0
    for line in lines:
        if used + len(line) > size and current:
            parts.append("\n".join(current))
            current, used = [], 0
        current.append(line)
        used += len(line) + 1
    parts.append("\n".join(current))
    out: list[dict[str, Any]] = []
    for n, part in enumerate(parts[: _env_int("AX_MAX_PARTS", 6)], start=1):
        note = (f"This is part {n} of {len(parts)} of the page: return the rows found in this part only.\n" if len(parts) > 1 else "")
        note += "The page is given as its accessibility tree: a table row is one line `row: cell | cell`, a card or list item is one line."
        ctx = json.dumps({"page_url": page_url, "accessibility_tree": part}, ensure_ascii=False)
        prompt = _prompt(intent, columns, label_hint, page_url=page_url, source_name=source_name, context=ctx, note=note)
        try:
            out += _rows_from(gemini_json(prompt, temperature=float(os.getenv("GEMINI_SCRAPE_TEMPERATURE", "0.15"))), columns)
        except Exception as e:  # noqa: BLE001 - one part lost, the rest kept
            logger.warning("Tree part %d of %d could not be read: %s", n, len(parts), e)
    return out


def gemini_extract_rows_from_page(
    html: str,
    intent: ScrapeIntent,
    columns: list[str],
    *,
    page_url: str = "",
    source_name: str = "",
    column_labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Primary scrape extractor: the model reads the page context and returns rows."""
    if len(html) < 400 or not columns:
        return []

    labels = column_labels or columns
    label_hint = json.dumps(dict(zip(columns, labels)), ensure_ascii=False)

    tables = extract_tables_from_html(html)
    main = max(tables, key=lambda t: len(t["rows"]), default=None)
    if main is not None and len(main["rows"]) > _env_int("GEMINI_SCRAPE_CHUNK_ROWS", 60):
        rows = _extract_big_table(main, intent, columns, label_hint, page_url=page_url, source_name=source_name)
        if rows:
            return rows

    ctx = build_gemini_page_context(html, page_url=page_url)
    ctx_json = json.dumps(ctx, default=str)
    max_ctx = _env_int("GEMINI_SCRAPE_CONTEXT_CHARS", 180000)
    if len(ctx_json) > max_ctx:
        ctx_json = ctx_json[:max_ctx]

    prompt = _prompt(intent, columns, label_hint, page_url=page_url, source_name=source_name, context=ctx_json)
    try:
        data = gemini_json(prompt, temperature=float(os.getenv("GEMINI_SCRAPE_TEMPERATURE", "0.15")))
    except Exception as e:
        logger.warning("Gemini scrape extract failed: %s", e)
        return []
    return _rows_from(data, columns)
