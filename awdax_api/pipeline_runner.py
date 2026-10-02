from __future__ import annotations

import os
from typing import Any, Callable

from discovery import SourceCandidate
from inspector import ScrapePlan, discover_inspected_sources
from query_generation import generate_search_queries
from reasoning import ScrapeIntent, parse_prompt
from regulatory_strategy import (
    intent_uses_regulatory_feed,
    regulatory_feed_max_pages,
    regulatory_feed_table_schema,
)
from scraper import ScrapeJob, universal_service


class InstanceDeleted(RuntimeError):
    """The chat was deleted while its run was in progress."""


ProgressFn = Callable[[str, str, str], None]
SourceFn = Callable[[str, dict[str, Any]], None]
JobFn = Callable[[str, str], None]


def run_pipeline_for_session(
    sess: dict[str, Any],
    goal: str,
    *,
    on_progress: ProgressFn | None = None,
    on_source: SourceFn | None = None,
    on_job: JobFn | None = None,
    max_pages: int | None = None,
) -> dict[str, Any]:
    def prog(phase: str, detail: str) -> None:
        if on_progress:
            on_progress(sess["id"], phase, detail)

    prog("planning", "Understanding your request…")
    intent = parse_prompt(goal)
    sess["intent"] = intent.to_dict()
    sess["job_id"] = intent.job_id
    job_id = intent.job_id
    if job_id and on_job:
        on_job(sess["id"], job_id)
    if job_id:
        universal_service.clear_job_dataset(job_id)

    prog("planning", "Generating search queries…")
    queries = generate_search_queries(intent)
    sess["search_queries"] = [q.to_dict() for q in queries]

    prog("discovery", "Discovering and inspecting sources…")

    def _discover_progress(msg: str) -> None:
        phase = "rendering" if msg.startswith(("Inspecting", "Anchor inspect")) else "discovery"
        prog(phase, msg)

    def _discovered(source: dict[str, Any]) -> None:
        if on_source:
            on_source(sess["id"], source)

    sources, plans = discover_inspected_sources(intent, on_progress=_discover_progress, on_source=_discovered, search_queries=queries)
    sess["sources"] = [s.to_dict() for s in sources]
    sess["plans"] = [p.to_dict() for p in plans]
    sess["plan"] = plans[0].to_dict() if plans else None

    if intent_uses_regulatory_feed(intent):
        sess["table_schema"] = regulatory_feed_table_schema()
    else:
        prog("rendering", "Proposing table schema…")
        from table_schema import propose_table_schema

        sess["table_schema"] = propose_table_schema(intent, plans)

    pages = regulatory_feed_max_pages(max_pages) if intent_uses_regulatory_feed(intent) else int(
        max_pages or os.getenv("SCRAPE_MAX_PAGES", "3")
    )

    if intent_uses_regulatory_feed(intent):
        prog("extracting", "RegulatoryFeed scrape (eGazette listing + PDF)…")
        from RegulatoryFeed import feed_service

        before_ids = {it.get("id") for it in feed_service.list_feed(limit=500)}
        feed_service.trigger_scrape(max_pages=pages)
        sess["regulatory_feed_active"] = True
        return sess

    if not plans:
        raise RuntimeError("No inspected sources found for this request")

    job = ScrapeJob(
        job_id=intent.job_id,
        intent=intent,
        plans=plans,
        plan=plans[0],
        status="ready",
        table_schema=sess.get("table_schema"),
    )
    universal_service.save_job(job)
    live = _live_flag_from_store(sess)
    prog("extracting", f"Scraping {len(plans)} source(s)…")
    universal_service.trigger_scrape_all(plans, job, max_pages=pages, live=live)
    return sess


def _live_flag_from_store(sess: dict[str, Any]) -> bool:
    """Read keep_live fresh: the user may have paused (or deleted the chat) since the run started."""
    from awdax_api.session_store import load_instance_session

    latest = load_instance_session(sess["id"])
    if latest is None:
        raise InstanceDeleted(sess["id"])
    return bool(latest.get("keep_live"))
