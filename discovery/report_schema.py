"""Canonical validated-source report (same shape on every run)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from discovery.scrape_schema import ScrapeInstructionSet


class ReportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class AccessMethod(str, Enum):
    HTTP_STATIC = "http_static"
    FILE_DOWNLOAD = "file_download"
    API = "api"
    JS_RENDERED = "js_rendered"
    LOGIN_REQUIRED = "login_required"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class DataCompleteness(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    UNCLEAR = "unclear"


class ValidatedSourceItem(BaseModel):
    rank: int = Field(ge=1)
    url: str
    title: str
    access_method: AccessMethod
    data_completeness: DataCompleteness
    quality_score: int = Field(ge=1, le=10)
    authority_score: int = Field(ge=1, le=10)
    relevance_score: int = Field(ge=1, le=10)
    format: Literal["html_table", "pdf", "csv", "xlsx", "json_api", "dashboard", "mixed", "other"]
    likely_fields: list[str] = Field(default_factory=list, max_length=20)
    pages_inspected: int = Field(ge=1, default=1)
    extraction_notes: str


class RejectedSourceItem(BaseModel):
    url: str
    title: str
    reason: str


class SourceInspectionBlock(BaseModel):
    """Step 2: what the bot saw + how to extract (fixed shape per source)."""

    url: str
    page_title: str
    what_we_see: str
    page_structure: list[str] = Field(default_factory=list)
    best_extraction_method: str
    extraction_query: str
    expected_columns: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    confidence: int = Field(ge=1, le=10, default=5)
    dom_region_selectors: list[str] = Field(default_factory=list)
    scrape_instructions: ScrapeInstructionSet | None = None
    probable_rows: int = Field(default=0, ge=0)


class ValidatedSourceReport(BaseModel):
    """Fixed top-level report returned by validation."""

    goal_summary: str
    status: ReportStatus
    min_sources_target: int
    validated_count: int
    validated_sources: list[ValidatedSourceItem] = Field(default_factory=list)
    rejected_sources: list[RejectedSourceItem] = Field(default_factory=list)
    dork_queries_used: list[str] = Field(default_factory=list)
    source_inspections: list[SourceInspectionBlock] = Field(default_factory=list)
    probable_rows_total: int = Field(default=0, ge=0)
    probable_rows_reason: str = ""
    procedure_notes: str = Field(
        default="Headless browser visited candidate URLs and related links; "
        "sources ranked by extractability and authority."
    )
