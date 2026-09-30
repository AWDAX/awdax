"""
Propose canonical output table columns for a scrape job.
"""

from __future__ import annotations

import json
from typing import Any

from inspector import ScrapePlan
from reasoning import ScrapeIntent, gemini_json
from table_merge import default_columns, _header_label


def propose_table_schema(
    intent: ScrapeIntent,
    plans: list[ScrapePlan] | None = None,
) -> dict[str, Any]:
    plans = plans or []
    sample_urls = [p.source_url or p.entry_url for p in plans[:6] if p]
    fallback_cols = default_columns(intent)

    prompt = f"""Define the ONE merged output table for scraping this user goal.

User goal: {intent.raw_prompt or intent.topic}
Desired fields from intent: {json.dumps(intent.output_fields or [])}

Sample source URLs we will scrape:
{json.dumps(sample_urls, indent=2)}

Return JSON object:
- columns: array of snake_case field keys (4-8 columns), e.g. car_name, price, range_km, battery, source
- column_labels: array of human-readable headers (same length as columns)
- description: one sentence on what each row represents

Focus on columns needed to list ALL items with prices/specs when relevant."""

    try:
        data = gemini_json(prompt)
        if isinstance(data, dict) and isinstance(data.get("columns"), list):
            cols = [str(c).strip() for c in data["columns"] if str(c).strip()]
            labels = data.get("column_labels") or []
            if len(labels) != len(cols):
                labels = [_header_label(c) for c in cols]
            else:
                labels = [str(l) for l in labels]
            if cols:
                return {
                    "columns": cols,
                    "column_labels": labels,
                    "description": str(data.get("description") or ""),
                }
    except Exception:
        pass

    return {
        "columns": fallback_cols,
        "column_labels": [_header_label(c) for c in fallback_cols],
        "description": f"Merged rows for: {intent.topic}",
    }
