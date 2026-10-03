"""
Generate Google search queries from the user's prompt.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from reasoning import ScrapeIntent, gemini_json
from regulatory_strategy import intent_uses_regulatory_feed, regulatory_feed_search_queries

# Queries that usually return shortlists, not full catalogs
_NARROW_RE = re.compile(
    r"|".join(
        [
            r"\bbest\b",
            r"\btop\s*\d+",
            r"\bcheapest\b",
            r"\bluxury\b",
            r"\bbudget\b",
            r"\bunder\s+[\d.]+\s*lakh",
            r"\bupcoming\b",
            r"\bnew launch",
            r"\bnewly launch",
            r"\breview\b",
            r"\bvs\b",
            r"\btata\b",
            r"\bmahindra\b",
            r"\bhyundai\b",
            r"\bmg motor\b",
            r"\bbyd\b",
            r"\bmaruti\b",
            r"\bkia\b",
            r"\btesla\b",
        ]
    ),
    re.I,
)


@dataclass
class GeneratedQuery:
    query: str
    rationale: str = ""
    source_type_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str) -> GeneratedQuery:
        if isinstance(data, str):
            return cls(query=data.strip())
        return cls(
            query=str(data.get("query") or data.get("text") or "").strip(),
            rationale=str(data.get("rationale") or ""),
            source_type_hint=str(data.get("source_type_hint") or ""),
        )


def _user_prompt_text(intent: ScrapeIntent) -> str:
    return (intent.raw_prompt or intent.topic or "").strip()


def _wants_full_catalog(user_prompt: str, intent: ScrapeIntent | None = None) -> bool:
    if intent and intent_uses_regulatory_feed(intent):
        return False
    p = user_prompt.lower()
    if any(k in p for k in ("all ", "list", "every ", "complete", "full ", "entire")):
        return True
    if re.search(r"\bev\b|\belectric car|\belectric vehicle", p):
        return True
    return False


def _is_narrow_query(query: str) -> bool:
    return bool(_NARROW_RE.search(query))


def _purpose_block(user_prompt: str, intent: ScrapeIntent | None = None) -> str:
    if not _wants_full_catalog(user_prompt, intent):
        return "Each query should help find pages with structured data relevant to the request."
    return """Purpose: we need to scrape a COMPLETE catalog (every model), with prices/specs in tables or lists—not a shortlist.

Each search query must target pages that list ALL or MANY items together (comparison pages, full price lists, Wikipedia list articles, aggregator category pages).

Do NOT use: best, top N, cheapest, luxury, budget/under ₹X, single-brand (Tata/Mahindra/etc.), upcoming-only, or review roundups.

Keep each query short (under ~10 words), natural for Google—avoid long site: strings."""


def generate_search_queries(intent: ScrapeIntent, *, count: int | None = None) -> list[GeneratedQuery]:
    if intent_uses_regulatory_feed(intent):
        return [GeneratedQuery.from_dict(q) for q in regulatory_feed_search_queries()]

    n = count or min(int(intent.max_sources or 10), int(os.getenv("SEARCH_QUERY_COUNT", "10")))
    n = max(1, min(n, 10))
    user_prompt = _user_prompt_text(intent)

    prompt = f"""Give me {n} Google search queries based on this user request.

User request:
{user_prompt}

{_purpose_block(user_prompt, intent)}

Return JSON only: an array of {n} strings (each string is one search query)."""

    data = gemini_json(prompt)
    if isinstance(data, dict):
        data = data.get("queries") or data.get("search_queries") or data.get("items")
    if not isinstance(data, list):
        raise ValueError("Query generator did not return a JSON array")

    out: list[GeneratedQuery] = []
    seen: set[str] = set()
    for item in data:
        gq = GeneratedQuery.from_dict(item if isinstance(item, (dict, str)) else {"query": str(item)})
        if not gq.query:
            continue
        key = gq.query.lower()
        if key in seen:
            continue
        if _wants_full_catalog(user_prompt, intent) and _is_narrow_query(gq.query):
            continue
        seen.add(key)
        out.append(gq)
        if len(out) >= n:
            break

    if len(out) < n:
        out.extend(_fallback_queries(user_prompt, n - len(out), seen, intent))

    return out[:n]


def _fallback_queries(
    user_prompt: str, need: int, seen: set[str], intent: ScrapeIntent | None = None
) -> list[GeneratedQuery]:
    if _wants_full_catalog(user_prompt, intent):
        seeds = [
            "all electric cars in India price list",
            "complete list electric vehicles India prices specifications",
            "site:cardekho.com electric cars price list all models India",
            "site:carwale.com all electric cars India price",
            "site:91wheels.com electric cars price list India",
            "list of electric cars in India wikipedia",
            "electric car models India comparison price range table",
            "every electric passenger car India ex showroom price",
            "EV models available in India price battery range list",
            user_prompt,
        ]
    else:
        seeds = [
            user_prompt,
            f"{user_prompt} price list",
            f"{user_prompt} data table",
            f"{user_prompt} complete list",
        ]
    out: list[GeneratedQuery] = []
    for s in seeds:
        if len(out) >= need:
            break
        s = s.strip()
        if not s or s.lower() in seen:
            continue
        if _wants_full_catalog(user_prompt, intent) and _is_narrow_query(s):
            continue
        seen.add(s.lower())
        out.append(GeneratedQuery(query=s))
    return out
