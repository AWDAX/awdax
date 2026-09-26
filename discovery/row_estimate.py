"""Goal-level probable row estimate before extraction."""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from llm.gemini import GeminiError, generate_json

logger = logging.getLogger(__name__)


class GoalRowEstimate(BaseModel):
    probable_rows: int = Field(ge=0, le=50_000)
    reasoning: str = ""


_PROMPT = """Estimate how many distinct data rows a web extraction will likely produce.

User goal:
\"\"\"{user_goal}\"\"\"

Per-source DOM counts (may overlap across sites):
{per_source}

Return a single probable_rows for the **merged** dataset (dedupe across sources mentally).
Be realistic for catalog/list goals (e.g. EV models in India often dozens, not thousands).
"""


def estimate_goal_rows(
    user_goal: str,
    per_source_counts: list[tuple[str, int]],
) -> GoalRowEstimate:
    lines = "\n".join(f"- {url}: ~{n} rows" for url, n in per_source_counts) or "(no DOM counts)"
    if not per_source_counts or all(n == 0 for _, n in per_source_counts):
        fallback = 50
        return GoalRowEstimate(
            probable_rows=fallback,
            reasoning="No DOM row count yet; using conservative default.",
        )
    dom_sum = sum(n for _, n in per_source_counts)
    heuristic = min(dom_sum, max(per_source_counts, key=lambda x: x[1])[1] + 10)

    try:
        est = generate_json(
            _PROMPT.format(user_goal=user_goal, per_source=lines),
            GoalRowEstimate,
            temperature=0.2,
        )
        if est.probable_rows <= 0:
            est.probable_rows = heuristic
        return est
    except GeminiError as exc:
        logger.debug("Goal row estimate LLM skip: %s", exc)
        return GoalRowEstimate(
            probable_rows=heuristic,
            reasoning=f"From DOM probes (sum≈{dom_sum}, merged heuristic≈{heuristic}).",
        )
