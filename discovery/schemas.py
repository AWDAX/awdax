"""Structured outputs for the discovery agent."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DorkPlan(BaseModel):
    intent_summary: str = Field(description="What data the user wants, in one sentence.")
    dork_queries: list[str] = Field(
        description="Short keyword search queries, run on Bing, that find pages publishing this data.",
        min_length=1,
        max_length=8,
    )
    seed_urls: list[str] = Field(
        default_factory=list,
        description="Known legitimate URLs that may host this data (gov, official stats, APIs).",
    )


class SearchHit(BaseModel):
    url: str
    title: str
    snippet: str
    from_dork: str | None = None


class RankedSource(BaseModel):
    url: str
    title: str
    why_good: str = Field(description="Why this source is trustworthy and relevant.")
    data_format_guess: str = Field(
        description="Likely format: html_table, pdf, csv, api, dashboard, other."
    )
    authority_score: int = Field(ge=1, le=10, description="1=sketchy, 10=official/authoritative.")
    relevance_score: int = Field(ge=1, le=10)


class SourceRankingResult(BaseModel):
    summary: str
    sources: list[RankedSource] = Field(max_length=12)
