"""Render discovery + validation + site inspection report."""

from __future__ import annotations

from discovery.report_schema import ValidatedSourceReport


def format_validated_report(report: ValidatedSourceReport) -> str:
    lines = [
        "=== AWDAX SOURCE DISCOVERY ===",
        "",
        f"Goal: {report.goal_summary}",
        f"Status: {report.status.value}",
        f"Validated: {report.validated_count} / target {report.min_sources_target}",
        "",
        report.procedure_notes,
        "",
    ]
    if report.probable_rows_total:
        lines.append(f"Probable rows (before extract): ~{report.probable_rows_total}")
        if report.probable_rows_reason:
            lines.append(f"  {report.probable_rows_reason}")
        lines.append("")

    if report.dork_queries_used:
        lines.append("Discovery strategies (reference — URLs come from headless search results):")
        for q in report.dork_queries_used:
            lines.append(f"  • {q}")
        lines.append("")

    lines.append(f"VALIDATED SOURCES ({len(report.validated_sources)})")
    lines.append("---")
    if not report.validated_sources:
        lines.append("(none)")
    else:
        inspections_by_url = {b.url.rstrip("/"): b for b in report.source_inspections}
        for src in sorted(report.validated_sources, key=lambda s: s.rank):
            fields = ", ".join(src.likely_fields) if src.likely_fields else "—"
            lines.extend(
                [
                    f"[{src.rank}] {src.title}",
                    f"URL: {src.url}",
                    f"Access: {src.access_method.value}",
                    f"Quality: {src.quality_score}/10 · Authority: {src.authority_score}/10 · "
                    f"Relevance: {src.relevance_score}/10",
                    f"Completeness: {src.data_completeness.value} · Format: {src.format}",
                    f"Pages inspected: {src.pages_inspected}",
                    f"Likely fields: {fields}",
                    f"Notes: {src.extraction_notes}",
                    "",
                ]
            )
            block = inspections_by_url.get(src.url.rstrip("/")) or inspections_by_url.get(src.url)
            if block:
                lines.append("  Site inspection (headless):")
                lines.append(f"  What we see: {block.what_we_see}")
                if block.page_structure:
                    lines.append("  Structure:")
                    for fact in block.page_structure:
                        lines.append(f"    - {fact}")
                lines.append(f"  Best extraction: {block.best_extraction_method} (confidence {block.confidence}/10)")
                if block.expected_columns:
                    lines.append(f"  Expected columns: {', '.join(block.expected_columns)}")
                if block.blockers:
                    lines.append(f"  Blockers: {'; '.join(block.blockers)}")
                lines.append("  Extraction query:")
                for qline in block.extraction_query.strip().splitlines():
                    lines.append(f"    {qline}")
                if block.dom_region_selectors:
                    lines.append("  Data discovery (DOM regions):")
                    for sel in block.dom_region_selectors:
                        lines.append(f"    - {sel}")
                if block.scrape_instructions:
                    si = block.scrape_instructions
                    lines.append("  Scrape instructions:")
                    lines.append(f"    List container: {si.list_container}")
                    lines.append(f"    Row selector: {si.row_selector}")
                    for f in si.fields:
                        lines.append(f"    • column `{f.column}` ← `{f.selector}` ({f.attr})")
                    if si.detail_page.enabled:
                        lines.append(
                            f"    Detail pages: yes — `{si.detail_page.link_selector}` "
                            f"(max {si.detail_page.max_visits})"
                        )
                    if si.probable_row_count:
                        lines.append(f"    Probable rows at source: ~{si.probable_row_count}")
                    if si.steps_human:
                        lines.append("    Steps:")
                        for step in si.steps_human:
                            lines.append(f"      {step}")
                lines.append("")

    if report.source_inspections and not report.validated_sources:
        lines.append("SITE INSPECTIONS")
        lines.append("---")
        for block in report.source_inspections:
            lines.extend(_format_inspection_block(block))
            lines.append("")

    rej_total = len(report.rejected_sources)
    rej_show = 5
    lines.append(f"REJECTED ({rej_total})")
    lines.append("---")
    if not report.rejected_sources:
        lines.append("(none)")
    else:
        for rej in report.rejected_sources[:rej_show]:
            lines.extend([f"• {rej.title}", f"  {rej.url}", f"  Reason: {rej.reason}", ""])
        if rej_total > rej_show:
            lines.append(f"  … and {rej_total - rej_show} more (noise URLs skipped in UI).")

    return "\n".join(lines).rstrip()


def _format_inspection_block(block) -> list[str]:
    lines = [
        f"• {block.page_title}",
        f"  URL: {block.url}",
        f"  What we see: {block.what_we_see}",
    ]
    if block.page_structure:
        lines.append("  Structure:")
        for fact in block.page_structure:
            lines.append(f"    - {fact}")
    lines.append(f"  Best extraction: {block.best_extraction_method}")
    lines.append("  Extraction query:")
    for qline in block.extraction_query.strip().splitlines():
        lines.append(f"    {qline}")
    return lines
