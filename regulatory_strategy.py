"""
eGazette / RegulatoryFeed execution strategy for the universal AI pipeline.

When the user wants Indian eGazette data, skip open-ended Google discovery and run the
same path as RegulatoryFeed: official listing scrape, PDF fetch, gazettes DB, AI summaries.
"""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from reasoning import ScrapeIntent

_EGAZETTE_RE = re.compile(r"\b(e[\-\s]?gazette|egazz?et|gazette)s?\b|egazette\.gov", re.I)


def _intent_blob(intent: ScrapeIntent) -> str:
    return " ".join(
        [
            intent.raw_prompt,
            intent.topic,
            intent.geography,
            " ".join(intent.named_sites),
            " ".join(intent.constraints),
            " ".join(intent.entity_types),
        ]
    ).lower()


def intent_uses_regulatory_feed(intent: ScrapeIntent | None) -> bool:
    if not intent:
        return False
    # Only the user's own words decide; model-written fields (pipeline, named_sites, ...) are ignored.
    user_text = (intent.raw_prompt or "").strip() or (intent.topic or "")
    return bool(_EGAZETTE_RE.search(user_text))


def enrich_intent_for_execution(intent: ScrapeIntent) -> ScrapeIntent:
    """Rule-based overrides after Gemini parse — aligns AI routing with RegulatoryFeed."""
    if not intent_uses_regulatory_feed(intent):
        if (intent.pipeline or "").strip() == "regulatory_feed":
            intent.pipeline = "universal"
        return intent
    intent.pipeline = "regulatory_feed"
    intent.max_sources = 1
    sites = list(intent.named_sites or [])
    if not any("egazette" in (s or "").lower() for s in sites):
        sites.append("https://egazette.gov.in")
    intent.named_sites = sites
    constraints = list(intent.constraints or [])
    official = "official egazette.gov.in listing only"
    if official not in [c.lower() for c in constraints]:
        constraints.append(official)
    intent.constraints = constraints
    if not intent.freshness:
        intent.freshness = "latest"
    return intent


def regulatory_feed_max_pages(explicit: int | None = None) -> int:
    if explicit is not None:
        return max(1, int(explicit))
    return int(os.getenv("REGULATORY_SCRAPE_MAX_PAGES", os.getenv("SCRAPE_MAX_PAGES", "3")))


def regulatory_feed_table_schema() -> dict[str, Any]:
    return {
        "columns": [
            "ministry",
            "subject",
            "issue_date",
            "publish_date",
            "gazette_id",
        ],
        "column_labels": [
            "Ministry / Organization",
            "Subject",
            "Issue Date",
            "Publish Date",
            "Gazette ID",
        ],
        "description": "Official eGazette listing (RegulatoryFeed pipeline)",
    }


def regulatory_feed_search_queries() -> list[dict[str, str]]:
    return [
        {
            "query": "site:egazette.gov.in gazette notifications",
            "rationale": "Official eGazette portal (RegulatoryFeed skips broad search)",
            "source_type_hint": "government",
        }
    ]


def egazette_regulatory_discovery(
    intent: ScrapeIntent,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[Any], list[Any]]:
    from discovery import SourceCandidate
    from inspector import egazette_preset_plan

    def _log(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    _log("RegulatoryFeed mode: official eGazette preset (no multi-site discovery)")
    url = "https://egazette.gov.in"
    source = SourceCandidate(
        url=url,
        final_url=url,
        title="eGazette India",
        snippet=intent.topic or "Indian government gazette notifications",
        relevance_score=1.0,
        legit_score=1.0,
        legit_reason="RegulatoryFeed canonical source",
        verified_search=True,
        domain="egazette.gov.in",
        https_ok=True,
        source_category="government",
        search_query="regulatory_feed",
    )
    plan = egazette_preset_plan()
    plan.source_url = url
    plan.dry_run_rows = 0
    return [source], [plan]
