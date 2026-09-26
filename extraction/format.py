"""Format extraction results for chat output."""

from __future__ import annotations

from extraction.models import ExtractionRunResult

def _markdown_table(columns: list[str], rows: list[list[str]]) -> list[str]:
    if not columns:
        return ["(empty table)"]
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    lines = [header, sep]
    for row in rows:
        padded = row + [""] * (len(columns) - len(row))
        cells = [c.replace("|", "\\|") for c in padded[: len(columns)]]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def format_extraction_result(result: ExtractionRunResult) -> str:
    lines = [
        "=== AWDAX EXTRACTION ===",
        "",
        result.summary,
        "",
    ]

    if result.probable_rows_total:
        lines.append(f"Expected rows (pre-extract): ~{result.probable_rows_total}")
        if result.probable_rows_reason:
            lines.append(f"Estimate: {result.probable_rows_reason}")
        lines.append(f"Actual rows extracted: {result.actual_rows_total}")
        lines.append("")

    if result.columns_chosen:
        lines.append(f"Columns: {', '.join(result.columns_chosen)}")
        if result.column_rationale:
            lines.append(f"Rationale: {result.column_rationale}")
        lines.append("")

    if result.cooked_new_code:
        lines.append("New code: YES — coding agent generated a custom extractor (see paths below).")
    else:
        lines.append("New code: no — used preexisting extractors.")
    lines.append("")

    if result.extractors_used:
        lines.append("Extractors / methods:")
        for ex in result.extractors_used:
            tag = "NEW" if ex.is_new else "existing"
            lines.append(f"  • [{tag}] {ex.extractor_id} via {ex.method_used} — {ex.path}")
            if ex.notes:
                lines.append(f"    {ex.notes}")
        lines.append("")

    if result.fill_checks:
        lines.append("Fill validation (agent):")
        for fc in result.fill_checks:
            lines.append(
                f"  • {fc.source_url} — **{fc.status}** "
                f"(fill rate {int(fc.fill_rate * 100)}%)"
            )
            if fc.agent_summary:
                lines.append(f"    {fc.agent_summary}")
            for issue in fc.issues[:4]:
                lines.append(f"    - {issue}")
        lines.append("")

    master = result.master_table
    if master and master.row_count:
        lines.append(f"--- Master dataset ({master.row_count} rows) ---")
        lines.append("All sources merged; `source` and `source_url` identify origin.")
        lines.append("")
        lines.extend(_markdown_table(master.columns, master.rows))
        lines.append("")
    elif not result.tables:
        lines.append("No tables to display.")
        return "\n".join(lines).rstrip()

    return "\n".join(lines).rstrip()
