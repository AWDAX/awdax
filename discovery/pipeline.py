"""Discovery + browser validation pipeline."""

from __future__ import annotations

import logging

from config.settings import settings
from discovery.discover import _plan_dorks, _rank_sources
from discovery.filters import filter_and_rank_hits
from discovery.format_report import format_validated_report
from discovery.gather import gather_candidates
from discovery.report_schema import ReportStatus, SourceInspectionBlock, ValidatedSourceReport
from discovery.schemas import SearchHit
from discovery.row_estimate import estimate_goal_rows
from inspector.deep_inspect import inspect_validated_sources
from extraction.engine import run_extraction
from extraction.format import format_extraction_result
from inspector.validate import validate_candidates
from llm.gemini import GeminiError

logger = logging.getLogger(__name__)


def _merge_reports(into: ValidatedSourceReport, batch: ValidatedSourceReport) -> None:
    seen_valid = {v.url.rstrip("/") for v in into.validated_sources}
    for src in batch.validated_sources:
        key = src.url.rstrip("/")
        if key in seen_valid:
            continue
        seen_valid.add(key)
        into.validated_sources.append(src)

    seen_rej = {r.url.rstrip("/") for r in into.rejected_sources}
    for rej in batch.rejected_sources:
        key = rej.url.rstrip("/")
        if key in seen_rej:
            continue
        seen_rej.add(key)
        into.rejected_sources.append(rej)


def _rerank_validated(report: ValidatedSourceReport) -> None:
    report.validated_sources.sort(
        key=lambda s: (s.quality_score, s.authority_score + s.relevance_score),
        reverse=True,
    )
    for i, src in enumerate(report.validated_sources, start=1):
        src.rank = i
    report.validated_count = len(report.validated_sources)


def _set_status(report: ValidatedSourceReport) -> None:
    if report.validated_count >= report.min_sources_target:
        report.status = ReportStatus.SUCCESS
    elif report.validated_count > 0:
        report.status = ReportStatus.PARTIAL
    else:
        report.status = ReportStatus.FAILED


def run_validated_discovery(user_goal: str) -> ValidatedSourceReport:
    """Keep searching and inspecting until target validated sources or hard cap."""
    plan = _plan_dorks(user_goal)

    tried_strategies: set[str] = set()
    inspected_urls: set[str] = set()
    dork_offset = 0
    expansion_round = 0
    attempts = 0

    report = ValidatedSourceReport(
        goal_summary=plan.intent_summary,
        status=ReportStatus.FAILED,
        min_sources_target=settings.min_validated_sources,
        validated_count=0,
        dork_queries_used=list(plan.dork_queries),
    )

    while (
        report.validated_count < settings.min_validated_sources
        and attempts < settings.max_discovery_attempts
        and len(inspected_urls) < settings.max_total_urls_inspected
    ):
        attempts += 1
        raw_hits, dork_offset, strategies = gather_candidates(
            user_goal,
            plan,
            tried_queries=tried_strategies,
            skip_urls=inspected_urls,
            dork_offset=dork_offset,
            dork_batch=3,
            expansion_round=expansion_round,
        )
        tried_strategies.update(strategies)
        if not raw_hits:
            expansion_round += 1
            if expansion_round > settings.max_discovery_search_rounds:
                break
            continue
        hits = filter_and_rank_hits(user_goal, raw_hits)

        pending = [h for h in hits if h.url.rstrip("/") not in {u.rstrip("/") for u in inspected_urls}]
        if not pending:
            if dork_offset >= len(plan.dork_queries):
                break
            continue

        try:
            ranked = _rank_sources(user_goal, plan, pending[:25])
            ranked_urls = {s.url.rstrip("/") for s in ranked.sources}
            pending = [h for h in pending if h.url.rstrip("/") in ranked_urls] + [
                h for h in pending if h.url.rstrip("/") not in ranked_urls
            ]
        except GeminiError:
            logger.debug("Pre-rank skipped (attempt %s)", attempts)

        batch_size = min(settings.max_sources_to_inspect, settings.max_total_urls_inspected - len(inspected_urls))
        batch = pending[: max(batch_size, 1)]
        for h in batch:
            inspected_urls.add(h.url)

        batch_report = validate_candidates(user_goal, plan, batch)
        _merge_reports(report, batch_report)
        _rerank_validated(report)
        _set_status(report)
        if batch_report.goal_summary:
            report.goal_summary = batch_report.goal_summary

    _set_status(report)
    return report


def run_validated_discovery_message(user_goal: str) -> str:
    try:
        report = run_validated_discovery(user_goal)
        extraction_text = ""
        if report.validated_sources:
            report.source_inspections = inspect_validated_sources(user_goal, report)
            per_source = [(b.url, b.probable_rows) for b in report.source_inspections]
            goal_est = estimate_goal_rows(user_goal, per_source)
            report.probable_rows_total = goal_est.probable_rows
            report.probable_rows_reason = goal_est.reasoning
            report.procedure_notes = (
                "Step 1: search + validate sources. "
                "Step 2: inspect site + data discovery (exact DOM regions + scrape instructions). "
                "Step 3: extract via instructions. "
                "Step 4: fill-validation agent checks the sheet."
            )
            extraction = run_extraction(user_goal, report, probable_rows_total=report.probable_rows_total)
            extraction_text = "\n\n" + format_extraction_result(extraction)
        return format_validated_report(report) + extraction_text
    except GeminiError as exc:
        logger.warning("Discovery pipeline Gemini error: %s", exc)
        return (
            "Could not complete source discovery (Gemini error). "
            "Check GEMINI_API_KEY and restart.\n"
            f"Details: {exc}"
        )
    except Exception:
        logger.exception("Validated discovery failed")
        return "Source discovery failed unexpectedly. See server logs."
