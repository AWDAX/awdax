"""Candidate URLs from headless browser search (+ curated topic seeds as backup)."""

from __future__ import annotations

import logging

from discovery.browser_search import browser_search_queries, search_query_variants
from discovery.schemas import DorkPlan, SearchHit
from discovery.search import dedupe_hits, hits_from_urls
from discovery.seeds import topic_seed_urls

logger = logging.getLogger(__name__)


def gather_url_candidates(
    user_goal: str,
    plan: DorkPlan,
    *,
    skip_urls: set[str],
    expansion_round: int,
) -> list[SearchHit]:
    """
    URLs come from **headless search results**, not from LLM-invented links.

    ``plan.seed_urls`` / dork strings are not used as URLs — only logged as strategies.
    """
    _ = plan  # intent only; no AI URL list
    skip_norm = {u.rstrip("/") for u in skip_urls}

    queries = search_query_variants(user_goal, expansion_round)
    hits = browser_search_queries(queries, max_results_per_query=8)

    if len(hits) < 5 and expansion_round == 0:
        backup = hits_from_urls(
            topic_seed_urls(user_goal),
            title="Topic seed (curated)",
            snippet="Fallback listing URL — not from LLM.",
        )
        hits = dedupe_hits(hits + backup)

    hits = dedupe_hits(hits)
    return [h for h in hits if h.url.rstrip("/") not in skip_norm]
