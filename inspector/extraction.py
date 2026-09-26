"""Recommend best extraction approach from a site snapshot."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from inspector.snapshot import SiteSnapshot
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)


class ExtractionPlan(BaseModel):
    """Fixed per-source extraction plan (same fields every run)."""

    url: str
    page_title: str
    what_we_see: str = Field(description="Plain-language summary of what the bot saw on the site.")
    page_structure: list[str] = Field(
        default_factory=list,
        description="Bullet facts: tables, lists, filters, pagination, downloads.",
        max_length=12,
    )
    best_extraction_method: str = Field(
        description="One of: http_get, headless_dom, file_download, api_json, pdf_text, vision_navigation."
    )
    extraction_query: str = Field(
        description="Concrete extraction spec: selectors, API path, file URL, or step list the extractor should run."
    )
    expected_columns: list[str] = Field(default_factory=list, max_length=20)
    blockers: list[str] = Field(default_factory=list, max_length=8)
    confidence: int = Field(ge=1, le=10)


_EXTRACTION_PROMPT = """You are the AWDAX source inspector. The user wants to extract data for this goal:

\"\"\"{user_goal}\"\"\"

Headless browser snapshot (JSON):
{snapshot}

Write an ExtractionPlan for this URL.
- what_we_see: describe the page like you're briefing a colleague (2-4 sentences).
- page_structure: 3-8 short bullet strings grounded in the snapshot.
- best_extraction_method: pick the simplest approach that will work:
  http_get (static HTML), headless_dom (JS/listings), file_download (csv/pdf/xlsx link),
  api_json (XHR/JSON endpoint), pdf_text, vision_navigation (only if complex UI).
- extraction_query: ALWAYS use this exact multi-line template (fill in values):

METHOD=<best_extraction_method>
URL=<final URL to fetch>
TARGET=<css selector or API endpoint or file pattern>
COLUMNS=<comma-separated column names>
PAGINATION=<none | click:SELECTOR | scroll | api_offset>
NOTES=<one line implementation hint>

- expected_columns: fields the user likely needs for their goal.
- blockers: login, captcha, anti-bot, missing prices, etc. (empty if none).
- confidence: 1-10 that this plan will work.
"""


def _fallback_plan(snapshot: SiteSnapshot, user_goal: str) -> ExtractionPlan:
    s = snapshot.structure
    bullets: list[str] = []
    if s.table_summaries:
        bullets.append(f"Tables: {'; '.join(s.table_summaries[:3])}")
    if s.list_item_count:
        bullets.append(f"List items visible: ~{s.list_item_count}")
    if s.card_like_count:
        bullets.append(f"Card/article blocks: ~{s.card_like_count}")
    if s.has_pagination:
        bullets.append("Pagination controls detected")
    if s.has_filters:
        bullets.append("Filters or search inputs detected")
    if s.download_links:
        bullets.append(f"Download links: {s.download_links[0]}")

    method = "headless_dom"
    target = "table tr, [class*='card'], article"
    if s.download_links:
        low = s.download_links[0].lower()
        if low.endswith((".csv", ".xlsx", ".xls", ".pdf")):
            method = "file_download"
            target = s.download_links[0]

    if not snapshot.ok:
        method = "vision_navigation"
        target = "n/a"

    query = (
        f"METHOD={method}\n"
        f"URL={snapshot.final_url}\n"
        f"TARGET={target}\n"
        f"COLUMNS=model,price,variant\n"
        f"PAGINATION={'click:a[rel=next]' if s.has_pagination else 'none'}\n"
        f"NOTES=Heuristic plan from DOM snapshot; refine after first extract."
    )

    return ExtractionPlan(
        url=snapshot.url,
        page_title=snapshot.title,
        what_we_see=(
            f"Page title “{snapshot.title}”. "
            + (
                " ".join(bullets[:4])
                if bullets
                else (s.sample_text[:300] if s.sample_text else "Limited visible text.")
            )
        ),
        page_structure=bullets or ["Could not parse structure; page may be blocked or empty."],
        best_extraction_method=method,
        extraction_query=query,
        expected_columns=["model", "price"],
        blockers=[snapshot.error] if snapshot.error else [],
        confidence=4 if snapshot.ok else 2,
    )


def plan_extraction(user_goal: str, snapshot: SiteSnapshot) -> ExtractionPlan:
    prompt = _EXTRACTION_PROMPT.format(user_goal=user_goal.strip(), snapshot=snapshot.to_prompt_block())
    try:
        plan = generate_json(prompt, ExtractionPlan, temperature=0.2)
        plan.url = snapshot.url
        if not plan.page_title:
            plan.page_title = snapshot.title
        return plan
    except GeminiError as exc:
        logger.warning("Extraction planning failed for %s: %s", snapshot.url, exc)
        return _fallback_plan(snapshot, user_goal)
