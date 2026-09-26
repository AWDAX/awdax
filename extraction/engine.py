"""Run extraction via scrape instructions, then DOM fallback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from urllib.parse import urlparse

from discovery.report_schema import SourceInspectionBlock, ValidatedSourceReport
from discovery.scrape_schema import ScrapeInstructionSet
from extraction.codegen import cook_extractor, load_generated
from extraction.dom_extract import extract_dom
from extraction.fetch import fetch_headless
from extraction.instruction_runner import run_instructions
from extraction.models import ExtractedTable, ExtractorInfo, ExtractionRunResult, FillCheckSummary
from extraction.normalize import normalize_rows
from extraction.quality import filter_rows
from extraction.vision import extract_with_vision
from extraction.merge import merge_tables
from validation.fill_agent import validate_table_fill

logger = logging.getLogger(__name__)

_STD_COLUMNS = ["brand", "model", "ex_showroom_price", "range", "battery_capacity", "power"]


def _rows_to_table(name: str, source_url: str, rows: list[dict[str, str]]) -> ExtractedTable:
    normalized = normalize_rows(filter_rows(rows))
    table_rows = [[r.get(c, "") for c in _STD_COLUMNS] for r in normalized]
    return ExtractedTable(
        name=name,
        source_url=source_url,
        columns=list(_STD_COLUMNS),
        rows=table_rows,
        row_count=len(table_rows),
    )


def _extract_from_source(
    user_goal: str,
    source_title: str,
    plan_block: SourceInspectionBlock | None,
) -> tuple[ExtractedTable | None, ExtractorInfo, ScrapeInstructionSet | None]:
    url = plan_block.url if plan_block else ""
    instructions = plan_block.scrape_instructions if plan_block else None
    if not url:
        return None, ExtractorInfo(extractor_id="none", path="", method_used="none", notes="Missing URL"), None

    extractor_id = "scrape_instructions"
    path = "extraction/instruction_runner.py"
    is_new = False
    method_used = "instruction_runner"
    notes = "Executed data-discovery scrape instructions."
    raw_rows: list[dict[str, str]] = []

    if instructions:
        raw_rows = run_instructions(instructions)
        if len(filter_rows(raw_rows)) < 5 and instructions.detail_page.enabled is False:
            instructions.detail_page.enabled = True
            raw_rows = run_instructions(instructions)
            notes += " Retried with detail pages enabled."

    cleaned = filter_rows(raw_rows)
    if len(cleaned) < 5:
        raw_rows = extract_dom(url, selectors=instructions.list_container if instructions else None)
        cleaned = filter_rows(raw_rows)
        method_used = "dom_extract_fallback"
        path = "extraction/dom_extract.py"

    html = ""
    if len(cleaned) < 5:
        html, ok = fetch_headless(url, scroll=True)
        if ok and html:
            gen_path, spec = cook_extractor(user_goal, url, html, reason="Instruction extract sparse.")
            if gen_path and spec:
                mod = load_generated(gen_path)
                if mod and hasattr(mod, "extract"):
                    try:
                        raw_rows = mod.extract(html, url)
                        cleaned = filter_rows(raw_rows)
                        extractor_id = gen_path.stem
                        path = f"extractors/generated/{gen_path.name}"
                        is_new = True
                        method_used = "generated_extractor"
                    except Exception as exc:
                        logger.warning("Generated extractor failed: %s", exc)

    if len(cleaned) < 3:
        vision_rows = extract_with_vision(user_goal, url)
        cleaned = filter_rows(vision_rows)
        if cleaned:
            method_used = "vision_navigation"
            path = "extraction/vision/navigator.py"

    if not cleaned:
        return None, ExtractorInfo(
            extractor_id=extractor_id,
            path=path,
            is_new=is_new,
            method_used=method_used,
            notes="No valid rows.",
        ), instructions

    table = _rows_to_table(source_title or urlparse(url).netloc, url, cleaned)
    info = ExtractorInfo(
        extractor_id=extractor_id,
        path=path,
        is_new=is_new,
        method_used=method_used,
        notes=f"{notes} ({table.row_count} rows).",
    )
    return table, info, instructions


def run_extraction(
    user_goal: str,
    report: ValidatedSourceReport,
    *,
    probable_rows_total: int = 0,
    on_source_progress: Callable[[str, str], None] | None = None,
) -> ExtractionRunResult:
    inspections = {b.url.rstrip("/"): b for b in report.source_inspections}
    tables: list[ExtractedTable] = []
    extractors: list[ExtractorInfo] = []
    fill_checks: list[FillCheckSummary] = []
    cooked = False

    sources = sorted(report.validated_sources, key=lambda s: s.rank)
    if not sources:
        return ExtractionRunResult(user_goal=user_goal, columns_chosen=[], summary="No validated sources.")

    for src in sources[:3]:
        if on_source_progress:
            on_source_progress(src.title, f"Fetching data from {src.title}…")
        block = inspections.get(src.url.rstrip("/"))
        table, info, instructions = _extract_from_source(user_goal, src.title, block)
        if on_source_progress and table:
            on_source_progress(src.title, f"Got {table.row_count} rows from {src.title}")
        extractors.append(info)
        if info.is_new:
            cooked = True
        if not table or not table.row_count:
            continue

        fill = validate_table_fill(user_goal, table, instructions)
        fill_checks.append(
            FillCheckSummary(
                source_url=table.source_url,
                status=fill.status,
                fill_rate=fill.fill_rate,
                issues=fill.issues,
                agent_summary=fill.agent_summary or "; ".join(fill.issues[:3]),
            )
        )

        if fill.status != "success" and instructions and not instructions.detail_page.enabled:
            instructions.detail_page.enabled = True
            retry_rows = filter_rows(run_instructions(instructions))
            if len(retry_rows) > table.row_count:
                table = _rows_to_table(src.title, src.url, retry_rows)
                fill = validate_table_fill(user_goal, table, instructions)
                fill_checks[-1] = FillCheckSummary(
                    source_url=table.source_url,
                    status=fill.status,
                    fill_rate=fill.fill_rate,
                    issues=fill.issues,
                    agent_summary="Re-ran with detail pages after fill audit.",
                )

        tables.append(table)

    if not tables:
        return ExtractionRunResult(
            user_goal=user_goal,
            columns_chosen=list(_STD_COLUMNS),
            extractors_used=extractors,
            fill_checks=fill_checks,
            cooked_new_code=cooked,
            summary="Extraction produced no valid rows.",
        )

    master = merge_tables(tables)
    master_cols = master.columns if master else list(_STD_COLUMNS)
    total = master.row_count if master else sum(t.row_count for t in tables)
    probable = probable_rows_total or report.probable_rows_total
    ok = sum(1 for f in fill_checks if f.status == "success")
    return ExtractionRunResult(
        user_goal=user_goal,
        columns_chosen=master_cols,
        column_rationale="Merged master sheet with S. No., source, source_url, and shared data columns.",
        extractors_used=extractors,
        tables=tables,
        master_table=master,
        probable_rows_total=probable,
        probable_rows_reason=report.probable_rows_reason,
        actual_rows_total=total,
        fill_checks=fill_checks,
        cooked_new_code=cooked,
        summary=(
            f"Master dataset: {total} rows (expected ~{probable} before extract). "
            f"Sources merged: {len(tables)}. Fill audit: {ok}/{len(fill_checks)} passed."
        ),
    )
