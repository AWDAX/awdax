"""Collect candidate URLs for headless inspection from headless browser search."""

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

    Each attempt searches the next ``dork_batch`` planner queries from ``dork_offset``, skipping any
    already tried. When the plan runs out, fixed variants of the goal are searched instead.
    """
    round_idx = expansion_round if expansion_round is not None else (dork_offset // max(dork_batch, 1))
    strategies = plan.dork_queries[dork_offset : dork_offset + dork_batch]
    fresh = [q for q in strategies if q not in tried_queries]
    hits = gather_url_candidates(user_goal, plan, skip_urls=skip_urls, expansion_round=round_idx, queries=fresh)
    new_offset = dork_offset + dork_batch
    return hits, new_offset, strategies
