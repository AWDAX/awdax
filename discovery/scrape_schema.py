"""Precise scrape instructions (fixed shape)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FieldSelector(BaseModel):
    column: str
    selector: str = Field(description="CSS selector relative to row element.")
    attr: str = Field(default="text", description="text | href | attribute:name")


class DetailPagePlan(BaseModel):
    enabled: bool = False
    link_selector: str = Field(default="a[href]", description="Within each row, link to detail page.")
    max_visits: int = Field(default=25, ge=0, le=100)
    fields: list[FieldSelector] = Field(default_factory=list)


class ScrapeInstructionSet(BaseModel):
    source_url: str
    list_container: str = Field(description="CSS selector for the block holding all rows, e.g. #popularElectricCars_0")
    row_selector: str = Field(description="CSS selector for each item, relative to list_container.")
    fields: list[FieldSelector] = Field(min_length=1)
    detail_page: DetailPagePlan = Field(default_factory=DetailPagePlan)
    steps_human: list[str] = Field(default_factory=list, max_length=12)
    probable_row_count: int = Field(default=0, ge=0, description="Rows expected from list container before extract.")


class DomRegionHint(BaseModel):
    selector: str
    element_id: str = ""
    tag: str = ""
    estimated_rows: int = 0
    sample_text: str = ""
    sample_links: list[str] = Field(default_factory=list)
