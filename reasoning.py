"""
Parse natural-language scrape requests into structured ScrapeIntent (JSON).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


@dataclass
class ScrapeIntent:
    job_id: str
    topic: str
    geography: str = ""
    entity_types: list[str] = field(default_factory=list)
    output_fields: list[str] = field(default_factory=list)
    freshness: str = ""
    language: str = "en"
    named_sites: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    max_sources: int = 10
    raw_prompt: str = ""
    pipeline: str = "universal"  # universal | regulatory_feed

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScrapeIntent:
        return cls(
            job_id=str(data.get("job_id") or uuid.uuid4().hex[:12]),
            topic=str(data.get("topic") or "").strip(),
            geography=str(data.get("geography") or ""),
            entity_types=list(data.get("entity_types") or []),
            output_fields=list(data.get("output_fields") or []),
            freshness=str(data.get("freshness") or ""),
            language=str(data.get("language") or "en"),
            named_sites=list(data.get("named_sites") or []),
            constraints=list(data.get("constraints") or []),
            max_sources=10,
            raw_prompt=str(data.get("raw_prompt") or ""),
            pipeline=str(data.get("pipeline") or "universal").strip() or "universal",
        )

    def validate(self) -> None:
        if not self.topic:
            raise ValueError("ScrapeIntent.topic is required")


def _gemini_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def gemini_json(prompt: str, *, temperature: float = 0.2) -> Any:
    if not GEMINI_AVAILABLE:
        raise RuntimeError("google-generativeai is not installed")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(_gemini_model_name())
    resp = model.generate_content(prompt)
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def parse_prompt(raw: str, *, job_id: str | None = None) -> ScrapeIntent:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Prompt cannot be empty")

    system = """You are a web scraping planner. Convert the user request into JSON with exactly these keys:
- topic (string, required, short)
- geography (string)
- entity_types (array of strings)
- output_fields (array of strings: fields they want captured)
- freshness (string: e.g. last 30 days, latest)
- language (string)
- named_sites (array of URLs or site names user mentioned)
- constraints (array: legal, rate limits, official sources only, etc.)
- max_sources (integer 1-10)
- pipeline (string: "universal" or "regulatory_feed")

Be specific. If regulatory/government data, prefer official sources in constraints.

If the user wants Indian eGazette / egazette.gov.in notifications (latest gazettes, ministry notifications):
- set pipeline to "regulatory_feed"
- set max_sources to 1
- set named_sites to include "https://egazette.gov.in"
- set freshness to "latest" when they ask for recent/latest data

If the user wants a comprehensive list (e.g. all EV cars with prices, compare models nationwide):
- set output_fields to explicit table headers they care about (e.g. car name, price, range)
- add constraint: prefer comparison/aggregator sites (CarWale, CarDekho, 91Wheels); avoid single-vendor OEM marketing sites"""
    prompt = f"{system}\n\nUser request:\n{raw}"
    data = gemini_json(prompt)
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object")

    intent = ScrapeIntent.from_dict(
        {
            **data,
            "job_id": job_id or uuid.uuid4().hex[:12],
            "raw_prompt": raw,
            "max_sources": min(int(data.get("max_sources") or 10), 10),
        }
    )
    intent.validate()
    from regulatory_strategy import enrich_intent_for_execution

    return enrich_intent_for_execution(intent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse scrape prompt → ScrapeIntent JSON")
    parser.add_argument("prompt", nargs="?", help="Natural language prompt")
    parser.add_argument("--out", "-o", help="Write JSON to file")
    args = parser.parse_args(argv)
    prompt = args.prompt or sys.stdin.read()
    intent = parse_prompt(prompt)
    out = json.dumps(intent.to_dict(), indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
