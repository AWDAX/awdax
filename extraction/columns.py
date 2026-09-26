"""Agent-chosen columns and row normalization."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from extraction.models import ExtractedTable
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)


class ColumnDecision(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=20)
    rationale: str


_PROMPT = """You decide final table columns for a data extraction goal.

User goal:
\"\"\"{user_goal}\"\"\"

Sample rows (JSON-like):
{sample}

Pick the best column order for the user's goal. Use clear names (model, brand, price_inr, range_km, body_type, etc.).
Return ColumnDecision JSON."""


def decide_columns(user_goal: str, raw_rows: list[dict[str, str]]) -> ColumnDecision:
    sample = raw_rows[:8]
    if not sample:
        return ColumnDecision(columns=["value"], rationale="No rows extracted; placeholder column.")
    try:
        return generate_json(
            _PROMPT.format(user_goal=user_goal, sample=sample),
            ColumnDecision,
            temperature=0.2,
        )
    except GeminiError:
        keys: list[str] = []
        for row in sample:
            for k in row:
                if k not in keys:
                    keys.append(k)
        return ColumnDecision(columns=keys[:12], rationale="Inferred from extracted row keys (Gemini unavailable).")


def rows_to_table(
    name: str,
    source_url: str,
    raw_rows: list[dict[str, str]],
    columns: list[str],
) -> ExtractedTable:
    rows: list[list[str]] = []
    for raw in raw_rows:
        rows.append([str(raw.get(col, "")).strip() for col in columns])
    return ExtractedTable(
        name=name,
        source_url=source_url,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )


def merge_column_decision(user_goal: str, tables: list[ExtractedTable]) -> tuple[list[str], str]:
    combined: list[dict[str, str]] = []
    for t in tables:
        for row in t.rows:
            combined.append({t.columns[i]: row[i] for i in range(min(len(t.columns), len(row)))})
    decision = decide_columns(user_goal, combined)
    return decision.columns, decision.rationale
