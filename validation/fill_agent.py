"""Verify extracted tables are filled; plan retries."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from discovery.scrape_schema import ScrapeInstructionSet
from extraction.models import ExtractedTable
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)


class FillValidationReport(BaseModel):
    status: str = Field(description="success | partial | failed")
    row_count: int = 0
    required_columns: list[str]
    empty_cells_by_column: dict[str, int] = Field(default_factory=dict)
    fill_rate: float = Field(ge=0, le=1, description="Fraction of required cells non-empty.")
    issues: list[str] = Field(default_factory=list)
    actions_taken: list[str] = Field(default_factory=list)
    agent_summary: str = ""


_REQUIRED_FOR_EV = ["model", "ex_showroom_price"]

_PROMPT = """You audit whether a scraped sheet satisfies the user's goal.

User goal:
\"\"\"{user_goal}\"\"\"

Required columns: {required}

Table: {rows} rows, columns {columns}
Empty counts by column: {empty}

Scrape plan summary:
{plan}

Return FillValidationReport JSON with status success if fill_rate>=0.85 and model+price mostly filled,
partial if usable but gaps, failed if unusable. List concrete issues and actions_taken (e.g. re-ran detail pages).
"""


def _empty_counts(table: ExtractedTable, columns: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {c: 0 for c in columns}
    col_index = {name: i for i, name in enumerate(table.columns)}
    for row in table.rows:
        for c in columns:
            idx = col_index.get(c)
            if idx is None or idx >= len(row) or not str(row[idx]).strip():
                counts[c] = counts.get(c, 0) + 1
    return counts


def validate_table_fill(
    user_goal: str,
    table: ExtractedTable,
    instructions: ScrapeInstructionSet | None,
    *,
    required: list[str] | None = None,
) -> FillValidationReport:
    required = required or _REQUIRED_FOR_EV
    present_required = [c for c in required if c in table.columns]
    if not present_required:
        present_required = list(required)

    empty = _empty_counts(table, present_required)
    total_cells = max(table.row_count * len(present_required), 1)
    filled = total_cells - sum(empty.values())
    fill_rate = round(filled / total_cells, 3)

    issues: list[str] = []
    if table.row_count < 5:
        issues.append(f"Only {table.row_count} rows (expected more for this goal).")
    for col, n in empty.items():
        if n > table.row_count * 0.4:
            issues.append(f"Column '{col}' empty in {n}/{table.row_count} rows.")

    status = "success"
    if fill_rate < 0.5 or table.row_count < 3:
        status = "failed"
    elif fill_rate < 0.85 or issues:
        status = "partial"

    plan_txt = ""
    if instructions:
        plan_txt = (
            f"container={instructions.list_container}; rows={instructions.row_selector}; "
            f"detail={instructions.detail_page.enabled}"
        )

    base = FillValidationReport(
        status=status,
        row_count=table.row_count,
        required_columns=present_required,
        empty_cells_by_column=empty,
        fill_rate=fill_rate,
        issues=issues,
        actions_taken=["Programmatic fill audit."],
        agent_summary="",
    )

    try:
        augmented = generate_json(
            _PROMPT.format(
                user_goal=user_goal,
                required=present_required,
                rows=table.row_count,
                columns=table.columns,
                empty=empty,
                plan=plan_txt,
            ),
            FillValidationReport,
            temperature=0.1,
        )
        augmented.fill_rate = fill_rate
        augmented.row_count = table.row_count
        augmented.empty_cells_by_column = empty
        if not augmented.required_columns:
            augmented.required_columns = present_required
        return augmented
    except GeminiError as exc:
        logger.debug("Fill agent LLM skip: %s", exc)
        base.agent_summary = "Fill checked with rules only (Gemini unavailable)."
        return base
