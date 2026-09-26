"""Step 2 + data discovery: site snapshot, DOM regions, scrape instructions."""

from __future__ import annotations

import logging

from discovery.report_schema import SourceInspectionBlock, ValidatedSourceReport
from inspector.extraction import plan_extraction
from inspector.scrape_planner import plan_scrape_instructions
from inspector.snapshot import capture_site_snapshot

logger = logging.getLogger(__name__)


def inspect_validated_sources(user_goal: str, report: ValidatedSourceReport) -> list[SourceInspectionBlock]:
    blocks: list[SourceInspectionBlock] = []
    for src in sorted(report.validated_sources, key=lambda s: s.rank):
        logger.info("Deep inspect + data discovery: %s", src.url)
        snapshot = capture_site_snapshot(src.url)
        plan = plan_extraction(user_goal, snapshot)
        scrape, regions = plan_scrape_instructions(user_goal, src.url)

        blocks.append(
            SourceInspectionBlock(
                url=plan.url,
                page_title=plan.page_title,
                what_we_see=plan.what_we_see,
                page_structure=plan.page_structure,
                best_extraction_method=plan.best_extraction_method,
                extraction_query=plan.extraction_query,
                expected_columns=plan.expected_columns,
                blockers=plan.blockers,
                confidence=plan.confidence,
                dom_region_selectors=[r.selector for r in regions[:6]],
                scrape_instructions=scrape,
                probable_rows=scrape.probable_row_count,
            )
        )
    return blocks
