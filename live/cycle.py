"""One live refresh cycle: discovery (once) + extract + merge."""

from __future__ import annotations

import json
import logging
from typing import Callable

from discovery.pipeline import run_validated_discovery
from discovery.row_estimate import estimate_goal_rows
from discovery.report_schema import ValidatedSourceReport
from extraction.engine import run_extraction
from extraction.format import format_extraction_result
from extraction.merge import merge_tables, upsert_master_table
from extraction.models import ExtractedTable
from discovery.format_report import format_validated_report
from inspector.deep_inspect import inspect_validated_sources
from live.types import LivePhase
from llm.gemini import GeminiError

logger = logging.getLogger(__name__)

ProgressFn = Callable[[LivePhase, str, str], None]


def _emit(progress: ProgressFn | None, phase: LivePhase, detail: str, source: str = "") -> None:
    if progress:
        progress(phase, detail, source)


def run_live_cycle(
    user_goal: str,
    *,
    report_json: str | None,
    master_json: str | None,
    progress: ProgressFn | None = None,
) -> tuple[str | None, str | None, str, int, int]:
    """
    Returns (report_json, master_json, chat_snippet, rows_total, rows_added).
    """
    report: ValidatedSourceReport | None = None
    if report_json:
        try:
            report = ValidatedSourceReport.model_validate_json(report_json)
        except Exception:
            logger.warning("Invalid report snapshot; re-running discovery")

    if report and report.validated_sources and not report.source_inspections:
        _emit(progress, LivePhase.INSPECT, "Re-inspecting sources after plan drift…")
        report.source_inspections = inspect_validated_sources(user_goal, report)

    if report is None or not report.validated_sources:
        _emit(progress, LivePhase.DISCOVERY, "Searching and validating sources…")
        try:
            report = run_validated_discovery(user_goal)
        except Exception as exc:
            logger.exception("Discovery failed")
            raise RuntimeError(f"Discovery failed: {exc}") from exc

        if not report.validated_sources:
            return None, master_json, "No validated sources yet; will retry on next cycle.", 0, 0

        _emit(progress, LivePhase.INSPECT, "Inspecting pages and building scrape plan…")
        report.source_inspections = inspect_validated_sources(user_goal, report)
        per_source = [(b.url, b.probable_rows) for b in report.source_inspections]
        goal_est = estimate_goal_rows(user_goal, per_source)
        report.probable_rows_total = goal_est.probable_rows
        report.probable_rows_reason = goal_est.reasoning
        report.procedure_notes = (
            "Live track: discovery + inspect cached; extract re-runs on each refresh."
        )
    else:
        _emit(progress, LivePhase.EXTRACT, "Re-fetching from cached sources…")

    def extract_progress(source_title: str, detail: str) -> None:
        _emit(progress, LivePhase.EXTRACT, detail, source_title)

    try:
        extraction = run_extraction(
            user_goal,
            report,
            probable_rows_total=report.probable_rows_total,
            on_source_progress=extract_progress,
        )
    except GeminiError as exc:
        raise RuntimeError(f"Extraction error: {exc}") from exc

    prior_master: ExtractedTable | None = None
    if master_json:
        try:
            prior_master = ExtractedTable.model_validate_json(master_json)
        except Exception:
            prior_master = None

    fresh_master = extraction.master_table or merge_tables(extraction.tables)
    if not fresh_master:
        rows_total = prior_master.row_count if prior_master else 0
        return report.model_dump_json(), master_json, extraction.summary, rows_total, 0

    _emit(progress, LivePhase.MERGE, "Merging new and changed rows…")
    merged, added = upsert_master_table(prior_master, fresh_master)
    merged_json = merged.model_dump_json()
    report_json_out = report.model_dump_json()

    if prior_master is None:
        chat = format_validated_report(report) + "\n\n" + format_extraction_result(extraction)
    else:
        chat = (
            f"**Live refresh** — {merged.row_count} total rows "
            f"(+{added} new or updated this cycle)."
        )

    return report_json_out, merged_json, chat, merged.row_count, added
