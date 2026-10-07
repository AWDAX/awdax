"""
Parse natural-language scrape requests into structured ScrapeIntent (JSON).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

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
    pipeline: str = "universal"  # universal | regulatory_feed | places
    # Settings of the Google Maps pipeline (places_strategy.reconcile_places_intent); empty otherwise.
    places: dict[str, Any] = field(default_factory=dict)

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
            places=dict(data["places"]) if isinstance(data.get("places"), dict) else {},
        )

    def validate(self) -> None:
        if not self.topic:
            raise ValueError("ScrapeIntent.topic is required")


def gemini_json(prompt: str, *, temperature: float = 0.2) -> Any:
    """Kept for its 12 call sites; routes through llm_client (NVIDIA first, then Gemini)."""
    from llm_client import llm_json

    return llm_json(prompt, temperature=temperature)


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
- pipeline (string: "universal", "regulatory_feed" or "places")
- places (object, only when pipeline is "places": search_terms, locations, near_me, target_count, extra_fields, lead_focus)

Be specific. Prefer official sources in constraints for government data.

Use pipeline "places" when the user wants a list of real-world businesses, venues, organisations or points of interest
at or near a location: shops, restaurants, cafes, clinics, salons, gyms, hotels, schools, agencies, "leads" or
"prospects" among local businesses, anything "near me" or "nearby". Google Maps ranks those places; do not scrape
websites for them. Use "universal" for product prices and specs, statistics, articles and datasets.
For pipeline "places" also fill the places object:
- search_terms: 1-8 short Google-Maps category phrases, e.g. "cafes", "dental clinics". When the user wants LEADS or
  PROSPECTS (they sell something to businesses, e.g. "leads for web development"), list the kinds of local business that
  would plausibly buy it (restaurants, clinics, salons, retail shops, coaching centres...), NOT competitors, unless asked.
- locations: every place the user named, as written; [] if none. For a big region or metro area (Delhi NCR, Greater Mumbai,
  Bay Area) list its main cities or districts instead, at most 8 (Delhi NCR: Delhi, Gurugram, Noida, Ghaziabad, Faridabad).
- near_me: true when they said near me / nearby, or named no place.
- target_count: how many places they want. "all", "every" or "complete list" means 300; a number they gave is used (at most
  300); otherwise 60.
- extra_fields: any of opening_hours, price_level, delivery, dine_in, takeout, vegetarian the user asked about.
- lead_focus: "" unless the request is about leads or prospects; then a short phrase for what the user sells.
- scrape_sites: true (the default) to also open each business's own website for its email, social links and site problems;
  false only if the user said not to.

Use pipeline "regulatory_feed" ONLY when the user explicitly asks for Indian eGazette /
egazette.gov.in gazette notifications (PDF listings, ministry notifications on the gazette portal).
Do NOT use regulatory_feed for Lok Sabha, Rajya Sabha, Sansad, or parliamentary session data —
those use pipeline "universal", named_sites like https://sansad.in and loksabha.nic.in / rajyasabha.nic.in,
and max_sources 6–10.

Set pipeline to "regulatory_feed" ONLY when the user explicitly mentions eGazette, egazette.gov.in or gazette notifications; otherwise "universal".
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
    from places_strategy import reconcile_places_intent
    from regulatory_strategy import enrich_intent_for_execution

    return reconcile_places_intent(enrich_intent_for_execution(intent))
