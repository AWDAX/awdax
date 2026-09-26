"""Build precise scrape instructions from DOM regions + user goal."""

from __future__ import annotations

import json
import logging

from discovery.scrape_schema import DetailPagePlan, DomRegionHint, FieldSelector, ScrapeInstructionSet
from extraction.count_probe import count_probable_rows
from inspector.dom_regions import scan_dom_regions
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)

_PROMPT = """You write precise scrape instructions for a headless extractor.

User goal:
\"\"\"{user_goal}\"\"\"

Page URL: {url}

DOM regions found (JSON — pick the best list container for the goal):
{regions}

Rules:
- list_container must be an exact selector from the regions list (prefer #id when present).
- row_selector is relative to list_container (e.g. li, tr, div.card).
- fields: column name + CSS selector relative to each row (model, ex_showroom_price, range, etc.).
- If listing rows lack detail, set detail_page.enabled=true with link_selector for car detail URLs.
- steps_human: 4-8 numbered plain steps the bot will follow.

Return ScrapeInstructionSet JSON."""


def _fallback_instructions(url: str, regions: list[DomRegionHint]) -> ScrapeInstructionSet:
    container = regions[0].selector if regions else "main"
    eid = regions[0].element_id if regions else ""
    steps = [
        f"Open {url} in headless browser.",
        f"Wait for list container `{container}`.",
        "For each row inside the container, read model name and price fields.",
    ]
    if "cardekho" in url:
        steps.append("If row lacks range/battery, open detail link and scrape specs.")
        return ScrapeInstructionSet(
            source_url=url,
            list_container=container or "#popularElectricCars_0",
            row_selector="li, div[class*='card'], tr",
            fields=[
                FieldSelector(column="model", selector="h3, a[title], [class*='title']"),
                FieldSelector(column="ex_showroom_price", selector="[class*='price' i], .price"),
                FieldSelector(column="range", selector="[class*='range' i]"),
            ],
            detail_page=DetailPagePlan(
                enabled=True,
                link_selector="a[href*='/car'], a[href*='/carmodels/']",
                max_visits=25,
                fields=[
                    FieldSelector(column="battery_capacity", selector="[class*='battery' i]"),
                    FieldSelector(column="power", selector="[class*='power' i], [class*='bhp' i]"),
                ],
            ),
            steps_human=steps,
        )

    return ScrapeInstructionSet(
        source_url=url,
        list_container=container,
        row_selector="li, article, tr, [class*='card']",
        fields=[
            FieldSelector(column="model", selector="h2, h3, a"),
            FieldSelector(column="ex_showroom_price", selector="[class*='price' i]"),
        ],
        detail_page=DetailPagePlan(
            enabled=True,
            link_selector="a[href]",
            max_visits=20,
            fields=[FieldSelector(column="ex_showroom_price", selector="[class*='price' i]")],
        ),
        steps_human=steps,
    )


def _attach_probable_count(inst: ScrapeInstructionSet, regions: list[DomRegionHint]) -> None:
    counted = count_probable_rows(inst.source_url, inst.list_container, inst.row_selector)
    if counted <= 0 and regions:
        counted = max(r.estimated_rows for r in regions)
    inst.probable_row_count = counted


def plan_scrape_instructions(user_goal: str, url: str) -> tuple[ScrapeInstructionSet, list[DomRegionHint]]:
    regions = scan_dom_regions(url)
    if not regions:
        inst = _fallback_instructions(url, [])
        _attach_probable_count(inst, regions)
        return inst, regions

    try:
        inst = generate_json(
            _PROMPT.format(
                user_goal=user_goal,
                url=url,
                regions=json.dumps([r.model_dump() for r in regions], ensure_ascii=False, indent=2),
            ),
            ScrapeInstructionSet,
            temperature=0.15,
        )
        inst.source_url = url
        if not inst.steps_human:
            inst.steps_human = _fallback_instructions(url, regions).steps_human
        _attach_probable_count(inst, regions)
        return inst, regions
    except GeminiError as exc:
        logger.warning("Scrape plan LLM failed: %s", exc)
        inst = _fallback_instructions(url, regions)
        _attach_probable_count(inst, regions)
        return inst, regions
