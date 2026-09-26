"""Validate discovered URLs via browser inspection + Gemini structured report."""

from __future__ import annotations

import logging
import re

from config.settings import settings
from discovery.report_schema import (
    AccessMethod,
    DataCompleteness,
    RejectedSourceItem,
    ReportStatus,
    ValidatedSourceItem,
    ValidatedSourceReport,
)
from discovery.schemas import DorkPlan, SearchHit
from discovery.filters import is_automotive_catalog_url
from inspector.browser import SourceInspection, inspect_candidates
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)

_URL_TITLE_RE = re.compile(r"^https?://", re.I)

_VALIDATION_PROMPT = """You validate web data sources for autonomous extraction.

User goal:
\"\"\"{user_goal}\"\"\"

Intent: {intent}

Minimum high-quality sources needed: {min_sources}

Below are headless-browser inspections (seed page + related download/data links).
For each seed URL decide: accept as validated source, or reject.

Accept if the site plausibly contains the requested data and is extractable:
- http_static: HTML tables or clear static content, no login
- file_download: direct CSV/PDF/XLS links found
- api: JSON/API endpoints visible in links or page text
- js_rendered: JS-heavy listings (CarDekho, CarWale, ZigWheels, Autocar) — ACCEPT for catalog goals
- login_required: password fields or login wall
- blocked: errors, captcha, inaccessible

For **catalog / price list** goals (cars, products with prices):
- ACCEPT major automotive listing sites even when js_rendered.
- Prefer pages that list model names and ex-showroom/on-road prices.

data_completeness: full | partial | unclear

Output ValidatedSourceReport JSON only:
- validated_sources: best sources first; **title** = human-readable page title (NEVER the raw URL string)
- rejected_sources: every other inspected seed URL with a short reason
- goal_summary: one sentence about the user's data need (not "validate sources")

Browser inspections:
{inspections}
"""


def _format_inspections(inspections: list[SourceInspection]) -> str:
    blocks: list[str] = []
    for ins in inspections:
        blocks.append(f"### Seed: {ins.seed_url} (title: {ins.seed_title})")
        for i, p in enumerate(ins.pages, start=1):
            blocks.append(
                f"Page {i}: {p.url}\n"
                f"  ok={p.ok} error={p.error}\n"
                f"  final_url={p.final_url}\n"
                f"  title={p.title}\n"
                f"  content_type={p.http_content_type}\n"
                f"  tables={p.table_count} password_field={p.has_password_field} login_hint={p.login_hint}\n"
                f"  downloads={p.download_links[:8]}\n"
                f"  data_links={p.data_links[:8]}\n"
                f"  excerpt={p.text_excerpt[:1200]!r}"
            )
        blocks.append("")
    return "\n".join(blocks)


def _inspection_map(inspections: list[SourceInspection]) -> dict[str, SourceInspection]:
    out: dict[str, SourceInspection] = {}
    for ins in inspections:
        out[ins.seed_url.rstrip("/")] = ins
    return out


def _fix_titles(report: ValidatedSourceReport, inspections: list[SourceInspection]) -> None:
    by_url = _inspection_map(inspections)
    for src in report.validated_sources:
        if _URL_TITLE_RE.match(src.title.strip()):
            ins = by_url.get(src.url.rstrip("/"))
            if ins and ins.seed_title and not _URL_TITLE_RE.match(ins.seed_title):
                src.title = ins.seed_title
            elif ins and ins.pages and ins.pages[0].title:
                src.title = ins.pages[0].title


def _account_for_all_inspected(
    report: ValidatedSourceReport,
    inspections: list[SourceInspection],
) -> None:
    """Ensure every inspected seed appears as validated or rejected."""
    validated_urls = {v.url.rstrip("/") for v in report.validated_sources}
    rejected_urls = {r.url.rstrip("/") for r in report.rejected_sources}

    for ins in inspections:
        key = ins.seed_url.rstrip("/")
        if key in validated_urls or key in rejected_urls:
            continue
        root = ins.pages[0] if ins.pages else None
        if root and root.ok and is_automotive_catalog_url(ins.seed_url):
            report.validated_sources.append(
                ValidatedSourceItem(
                    rank=len(report.validated_sources) + 1,
                    url=ins.seed_url,
                    title=root.title or ins.seed_title,
                    access_method=AccessMethod.JS_RENDERED,
                    data_completeness=DataCompleteness.PARTIAL,
                    quality_score=7,
                    authority_score=7,
                    relevance_score=8,
                    format="mixed",
                    likely_fields=["model", "price", "brand"],
                    pages_inspected=ins.pages_inspected,
                    extraction_notes="Auto-accepted automotive listing page after inspection.",
                )
            )
            validated_urls.add(key)
            continue
        reason = (root.error if root and root.error else "Not sufficient for the stated goal")
        report.rejected_sources.append(
            RejectedSourceItem(url=ins.seed_url, title=ins.seed_title, reason=reason)
        )


def _fallback_report(
    user_goal: str,
    plan: DorkPlan,
    inspections: list[SourceInspection],
    *,
    min_sources: int,
    error: str | None = None,
) -> ValidatedSourceReport:
    """Heuristic report when Gemini is unavailable."""
    validated: list[ValidatedSourceItem] = []
    rejected: list[RejectedSourceItem] = []

    for ins in inspections:
        root = ins.pages[0] if ins.pages else None
        if root is None:
            continue
        if not root.ok:
            rejected.append(
                RejectedSourceItem(url=ins.seed_url, title=ins.seed_title, reason=root.error or "Unreachable")
            )
            continue
        if root.has_password_field or root.login_hint:
            rejected.append(
                RejectedSourceItem(
                    url=ins.seed_url,
                    title=root.title,
                    reason="Login or sign-in likely required",
                )
            )
            continue

        access = AccessMethod.UNKNOWN
        fmt = "other"
        if root.download_links:
            access = AccessMethod.FILE_DOWNLOAD
            low = root.download_links[0].lower()
            if low.endswith(".pdf"):
                fmt = "pdf"
            elif low.endswith(".csv"):
                fmt = "csv"
            elif low.endswith((".xlsx", ".xls")):
                fmt = "xlsx"
        elif root.table_count > 0:
            access = AccessMethod.HTTP_STATIC
            fmt = "html_table"
        elif is_automotive_catalog_url(ins.seed_url):
            access = AccessMethod.JS_RENDERED
            fmt = "mixed"
        elif len(root.text_excerpt.strip()) < 200:
            access = AccessMethod.JS_RENDERED
            fmt = "dashboard"

        validated.append(
            ValidatedSourceItem(
                rank=len(validated) + 1,
                url=ins.seed_url,
                title=root.title or ins.seed_title,
                access_method=access,
                data_completeness=DataCompleteness.UNCLEAR,
                quality_score=7 if is_automotive_catalog_url(ins.seed_url) else 6,
                authority_score=7 if is_automotive_catalog_url(ins.seed_url) else 6,
                relevance_score=8 if is_automotive_catalog_url(ins.seed_url) else 6,
                format=fmt,  # type: ignore[arg-type]
                likely_fields=["model", "price"] if is_automotive_catalog_url(ins.seed_url) else [],
                pages_inspected=ins.pages_inspected,
                extraction_notes="Heuristic validation (Gemini unavailable).",
            )
        )

    validated.sort(key=lambda v: v.quality_score, reverse=True)
    validated = validated[: max(min_sources, 3)]
    for i, v in enumerate(validated, start=1):
        v.rank = i

    count = len(validated)
    if count >= min_sources:
        status = ReportStatus.SUCCESS
    elif count > 0:
        status = ReportStatus.PARTIAL
    else:
        status = ReportStatus.FAILED

    note = "Browser inspection only (heuristic scoring)."
    if error:
        note = f"{note} Gemini: {error}"

    return ValidatedSourceReport(
        goal_summary=plan.intent_summary or user_goal[:200],
        status=status,
        min_sources_target=min_sources,
        validated_count=count,
        validated_sources=validated,
        rejected_sources=rejected,
        dork_queries_used=list(plan.dork_queries),
        procedure_notes=note,
    )


def _finalize_report(
    report: ValidatedSourceReport,
    inspections: list[SourceInspection],
    *,
    min_sources: int,
) -> ValidatedSourceReport:
    _fix_titles(report, inspections)
    _account_for_all_inspected(report, inspections)
    report.validated_sources.sort(
        key=lambda s: (s.quality_score, s.authority_score + s.relevance_score),
        reverse=True,
    )
    for i, src in enumerate(report.validated_sources, start=1):
        src.rank = i
    report.validated_count = len(report.validated_sources)
    report.dork_queries_used = report.dork_queries_used or []
    if report.validated_count >= min_sources:
        report.status = ReportStatus.SUCCESS
    elif report.validated_count > 0:
        report.status = ReportStatus.PARTIAL
    else:
        report.status = ReportStatus.FAILED
    return report


def validate_candidates(
    user_goal: str,
    plan: DorkPlan,
    candidates: list[SearchHit],
    *,
    min_sources: int | None = None,
    max_inspect: int | None = None,
) -> ValidatedSourceReport:
    min_sources = min_sources if min_sources is not None else settings.min_validated_sources
    max_inspect = max_inspect if max_inspect is not None else settings.max_sources_to_inspect

    urls: list[str] = []
    seen: set[str] = set()
    for hit in candidates:
        key = hit.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        urls.append(hit.url)
        if len(urls) >= max_inspect:
            break

    inspections = inspect_candidates(urls)
    if not inspections:
        return ValidatedSourceReport(
            goal_summary=plan.intent_summary,
            status=ReportStatus.FAILED,
            min_sources_target=min_sources,
            validated_count=0,
            validated_sources=[],
            rejected_sources=[],
            dork_queries_used=list(plan.dork_queries),
            procedure_notes="No pages could be inspected (browser unavailable or no candidates).",
        )

    prompt = _VALIDATION_PROMPT.format(
        user_goal=user_goal.strip(),
        intent=plan.intent_summary,
        min_sources=min_sources,
        inspections=_format_inspections(inspections),
    )
    prompt += f"\n\ndork_queries_used (copy to output): {plan.dork_queries!r}\n"

    try:
        report = generate_json(prompt, ValidatedSourceReport, temperature=0.15)
        report.dork_queries_used = list(plan.dork_queries)
        return _finalize_report(report, inspections, min_sources=min_sources)
    except GeminiError as exc:
        logger.warning("Gemini validation failed, using heuristics: %s", exc)
        report = _fallback_report(user_goal, plan, inspections, min_sources=min_sources, error=str(exc))
        return _finalize_report(report, inspections, min_sources=min_sources)
