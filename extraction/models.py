"""Structured extraction output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExtractedTable(BaseModel):
    name: str
    source_url: str
    columns: list[str]
    rows: list[list[str]] = Field(default_factory=list)
    row_count: int = 0


class ExtractorInfo(BaseModel):
    extractor_id: str
    path: str
    is_new: bool = False
    method_used: str
    notes: str = ""


class FillCheckSummary(BaseModel):
    source_url: str
    status: str
    fill_rate: float = 0.0
    issues: list[str] = Field(default_factory=list)
    agent_summary: str = ""


class ExtractionRunResult(BaseModel):
    user_goal: str
    columns_chosen: list[str]
    column_rationale: str = ""
    extractors_used: list[ExtractorInfo] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    master_table: ExtractedTable | None = None
    probable_rows_total: int = 0
    probable_rows_reason: str = ""
    actual_rows_total: int = 0
    fill_checks: list[FillCheckSummary] = Field(default_factory=list)
    cooked_new_code: bool = False
    summary: str = ""
