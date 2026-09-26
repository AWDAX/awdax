"""Collect candidate URLs for headless inspection (no DuckDuckGo / search APIs)."""

from __future__ import annotations

from discovery.schemas import DorkPlan, SearchHit
from discovery.url_discovery import gather_url_candidates


def gather_candidates(
    user_goal: str,
    plan: DorkPlan,
    *,
    tried_queries: set[str],
    skip_urls: set[str],
    dork_batch: int = 4,
    dork_offset: int = 0,
    expansion_round: int | None = None,
) -> tuple[list[SearchHit], int, list[str]]:
    """
    Return URLs for the headless browser to open.

    ``dork_offset`` / ``dork_batch`` are kept for pipeline compatibility; dork strings
    from the planner are reference strategies only (not sent to a search engine).
    """
    _ = tried_queries, dork_batch
    round_idx = expansion_round if expansion_round is not None else (dork_offset // max(dork_batch, 1))
    hits = gather_url_candidates(user_goal, plan, skip_urls=skip_urls, expansion_round=round_idx)
    new_offset = dork_offset + dork_batch
    strategies = plan.dork_queries[dork_offset : dork_offset + dork_batch]
    return hits, new_offset, strategies
