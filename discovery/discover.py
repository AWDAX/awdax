"""Orchestrate dork generation, search, and source ranking."""

from __future__ import annotations

import logging

from discovery.schemas import DorkPlan, RankedSource, SearchHit, SourceRankingResult
from discovery.search import dedupe_hits, hits_from_urls
from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)

_DORK_PROMPT = """You are a web data acquisition expert. The user wants to track or collect data.

User request:
\"\"\"{user_goal}\"\"\"

If the goal is a **product/catalog listing** (e.g. cars with prices, SKUs, models):
- Prefer automotive publisher sites: site:cardekho.com, site:carwale.com, site:zigwheels.com, site:autocarindia.com
- Use queries like electric cars price list India, ex-showroom price, on-road price
- Do NOT use vague government portals (vahan, discom, generic india.gov) unless they clearly publish the catalog
- Seed URLs must be direct listing pages (electric car finder / price list), not homepages of unrelated agencies

If the goal is **statistics/time series** (sales, registrations, monthly trends):
- Prefer government open data, SIAM, regulator statistics, filetype:csv/pdf/xlsx

Produce 4–7 **discovery strategy** strings (Google-dork style hints for humans/logs — the bot does NOT run a search engine).
Optional **seed_urls** for logging only — runtime URL discovery uses headless search, not this list.
Avoid Wikipedia, encyclopedias, and generic electricity utility sites."""


_RANK_PROMPT = """You rank candidate web data sources for a tracking goal.

User goal:
\"\"\"{user_goal}\"\"\"

Intent: {intent}

Candidates (URL, title, snippet, found via dork):
{candidates}

Pick the best sources (up to 8). Match the goal type:
- Catalog/price list goals: strongly prefer CarDekho, CarWale, ZigWheels, Autocar India listing pages.
- Statistics goals: prefer official statistics and downloads.

Reject Wikipedia, encyclopedias, utility company homepages, and login-only portals.
For each source set **title** to the human page title (never paste the raw URL as title).
Give authority_score and relevance_score from 1–10."""


def _plan_dorks(user_goal: str) -> DorkPlan:
    return generate_json(_DORK_PROMPT.format(user_goal=user_goal.strip()), DorkPlan)


def _collect_candidates(
    plan: DorkPlan,
    *,
    dork_start: int = 0,
    dork_limit: int = 5,
    include_seeds: bool = True,
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    if include_seeds:
        hits.extend(
            hits_from_urls(
                plan.seed_urls,
                title="Seed (planner)",
                snippet="Opened directly in headless browser.",
            )
        )
    return dedupe_hits(hits)


def _format_candidates(hits: list[SearchHit]) -> str:
    lines: list[str] = []
    for i, h in enumerate(hits[:40], start=1):
        dork = h.from_dork or "seed"
        lines.append(
            f"{i}. URL: {h.url}\n   Title: {h.title}\n   Snippet: {h.snippet}\n   Dork: {dork}"
        )
    return "\n".join(lines) if lines else "(no search results — using seed URLs only)"


def _rank_sources(user_goal: str, plan: DorkPlan, hits: list[SearchHit]) -> SourceRankingResult:
    prompt = _RANK_PROMPT.format(
        user_goal=user_goal.strip(),
        intent=plan.intent_summary,
        candidates=_format_candidates(hits),
    )
    return generate_json(prompt, SourceRankingResult, temperature=0.2)


def discover_sources(user_goal: str) -> SourceRankingResult:
    """Find and rank data sources for a natural-language tracking goal."""
    plan = _plan_dorks(user_goal)
    hits = _collect_candidates(plan)
    if not hits:
        return SourceRankingResult(
            summary=(
                f"{plan.intent_summary} — no live search hits; add more specific terms or check network."
            ),
            sources=[
                RankedSource(
                    url=u,
                    title="Suggested seed URL",
                    why_good="From planner seed list (search returned nothing).",
                    data_format_guess="other",
                    authority_score=7,
                    relevance_score=6,
                )
                for u in plan.seed_urls[:5]
            ],
        )
    return _rank_sources(user_goal, plan, hits)


def format_discovery_message(result: SourceRankingResult, *, dork_queries: list[str] | None = None) -> str:
    lines = [
        "Source discovery",
        "",
        result.summary,
        "",
    ]
    if dork_queries:
        lines.append("Dorks used:")
        for q in dork_queries:
            lines.append(f"  • {q}")
        lines.append("")

    if not result.sources:
        lines.append("No strong sources found yet. Try narrowing the topic or region.")
        return "\n".join(lines)

    lines.append("Ranked sources:")
    for i, src in enumerate(
        sorted(
            result.sources,
            key=lambda s: (s.authority_score + s.relevance_score),
            reverse=True,
        ),
        start=1,
    ):
        lines.append(
            f"{i}. {src.title}\n"
            f"   {src.url}\n"
            f"   Authority {src.authority_score}/10 · Relevance {src.relevance_score}/10 · "
            f"Format: {src.data_format_guess}\n"
            f"   {src.why_good}"
        )
    return "\n".join(lines)


def run_discovery_for_message(user_goal: str) -> str:
    """End-to-end discovery + browser validation (fixed report format)."""
    from discovery.pipeline import run_validated_discovery_message

    return run_validated_discovery_message(user_goal)
