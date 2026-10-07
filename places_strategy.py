"""
Google Maps (Places) execution strategy: decide when a request is a search for real-world places, and the table it fills.

A request for local businesses, venues or "leads" (restaurants in Pune, clinics near me, prospects in Delhi NCR) has no
HTML table to scrape: Google Maps already ranks the places. This mirrors regulatory_strategy.py, which does the same
for eGazette: route the intent, then run its own pipeline (places_pipeline.py) instead of open-ended discovery.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from reasoning import ScrapeIntent
from regulatory_strategy import intent_is_parliament_sessions, intent_uses_regulatory_feed

logger = logging.getLogger(__name__)

PLACES_PIPELINE = "places"
DEFAULT_TARGET = 60
MAX_SEARCH_TERMS = 8

# What a request may ask for beyond the core columns: key -> (column key, label). Each also adds an API field
# (places_search.EXTRA_FIELD_MASKS); the atmosphere ones cost a higher Google tier, so they are opt-in.
EXTRA_COLUMNS: dict[str, tuple[str, str]] = {
    "opening_hours": ("hours", "Opening hours"),
    "price_level": ("price_level", "Price level"),
    "delivery": ("delivery", "Delivery"),
    "dine_in": ("dine_in", "Dine-in"),
    "takeout": ("takeout", "Takeout"),
    "vegetarian": ("vegetarian", "Serves vegetarian"),
}

CORE_COLUMNS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("category", "Category"),
    ("phone", "Phone"),
    ("website", "Website"),
    ("has_website", "Has website"),
    ("rating", "Rating"),
    ("reviews", "Reviews"),
    ("address", "Address"),
    ("area", "Area searched"),
    ("source_url", "Google Maps link"),
    ("business_status", "Status"),
]

# A request that reads as "find physical businesses near/in somewhere", used only to upgrade a request the model left
# on the web-scraping pipeline. Words are plural-or-singular business nouns; "near me"/"nearby" need no place name.
_PLACES_RE = re.compile(
    r"\b(near\s*me|nearby|near\s+by|leads?|prospects?|restaurants?|cafes?|caf[eé]s?|clinics?|salons?|gyms?|hotels?|"
    r"shops?|stores?|agenc(?:y|ies)|businesses|dentists?|doctors?|hospitals?|schools?|coaching\s+cent(?:er|re)s?|"
    r"bakeries|bakery|pharmac(?:y|ies)|boutiques?)\b",
    re.I,
)
_LEAD_RE = re.compile(r"\b(leads?|prospects?|clients?|customers?)\b", re.I)

MAX_LOCATIONS = 8
# A region name that Google reads as one huge area (Delhi NCR is about 55,000 km2, reaching Rohtak, Rewari and Alwar) puts the
# search tiles in the countryside around the real city. These are searched as their cities instead. The planner is asked to
# do the same for any region; this makes the most common one certain.
_METROS: dict[str, list[str]] = {
    "delhi ncr": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"],
    "ncr": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"],
    "national capital region": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"],
    "delhi/ncr": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"],
    "delhi-ncr": ["Delhi", "Gurugram", "Noida", "Ghaziabad", "Faridabad"],
}


def _expand_metro(locations: list[str]) -> list[str]:
    """A lone region name (Delhi NCR) becomes its main cities; anything else is left as given."""
    if len(locations) == 1:
        cities = _METROS.get(re.sub(r"\s+", " ", locations[0].strip().lower()))
        if cities:
            return list(cities)
    return locations


def maps_api_key() -> str:
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


def places_available() -> bool:
    return bool(maps_api_key())


def max_results() -> int:
    try:
        return max(1, int(os.getenv("PLACES_MAX_RESULTS", "300")))
    except ValueError:
        return 300


def intent_uses_places(intent: ScrapeIntent | None) -> bool:
    """True when the run is the Maps pipeline. The intent is only left on "places" when a Maps key exists."""
    if not intent or (intent.pipeline or "").strip() != PLACES_PIPELINE:
        return False
    return not intent_uses_regulatory_feed(intent)


def _clean_list(value: Any, *, limit: int, width: int = 80) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()[:width]
        if text and text.lower() not in (o.lower() for o in out):
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _target(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return min(DEFAULT_TARGET, max_results())
    return max(1, min(n, max_results()))


def reconcile_places_intent(intent: ScrapeIntent) -> ScrapeIntent:
    """Settle the routing after the model's parse: regulatory wins, a missing key falls back to web scraping, an
    obvious business search the model left on "universal" is upgraded, and the `places` settings are made safe."""
    prompt = (intent.raw_prompt or intent.topic or "").strip()
    wants_places = (intent.pipeline or "").strip() == PLACES_PIPELINE

    if intent_uses_regulatory_feed(intent) or intent_is_parliament_sessions(intent):
        intent.pipeline = "regulatory_feed" if intent_uses_regulatory_feed(intent) else "universal"
        return intent

    if not wants_places and (intent.pipeline or "universal") == "universal":
        from listing_sources import intent_wants_ev_catalog

        has_place = bool((intent.geography or "").strip()) or re.search(r"\bnear\s*me\b|\bnearby\b", prompt, re.I)
        if has_place and _PLACES_RE.search(prompt) and not intent_wants_ev_catalog(intent):
            wants_places = True

    if wants_places and not places_available():
        logger.info("Maps pipeline wanted but GOOGLE_MAPS_API_KEY is not set; using web discovery")
        wants_places = False
        if (intent.pipeline or "").strip() == PLACES_PIPELINE:
            intent.pipeline = "universal"

    if not wants_places:
        return intent

    raw = intent.places if isinstance(intent.places, dict) else {}
    terms = _clean_list(raw.get("search_terms"), limit=MAX_SEARCH_TERMS) or [intent.topic.strip() or prompt[:80]]
    locations = _clean_list(raw.get("locations"), limit=MAX_LOCATIONS)
    if not locations and (intent.geography or "").strip():
        locations = [intent.geography.strip()[:80]]
    locations = _expand_metro(locations)
    near_me = bool(raw.get("near_me")) or not locations
    lead_focus = str(raw.get("lead_focus") or "").strip()[:80]
    if not lead_focus and _LEAD_RE.search(prompt):
        lead_focus = intent.topic.strip()[:80] or "business"
    extras = [e for e in _clean_list(raw.get("extra_fields"), limit=len(EXTRA_COLUMNS)) if e in EXTRA_COLUMNS]
    # Open each business's own website for its email, social links and what is wrong with it: on unless the user said not
    # to, or the owner turned it off (PLACES_SCRAPE_SITES=0).
    scrape_sites = raw.get("scrape_sites") is not False and (os.getenv("PLACES_SCRAPE_SITES") or "1").strip().lower() not in ("0", "false", "no", "off")

    intent.pipeline = PLACES_PIPELINE
    intent.places = {
        "search_terms": terms,
        "locations": locations,
        "near_me": near_me and not locations,
        "target_count": _target(raw.get("target_count")),
        "extra_fields": extras,
        "lead_focus": lead_focus,
        "scrape_sites": scrape_sites,
    }
    intent.max_sources = 1
    return intent


def places_table_schema(intent: ScrapeIntent) -> dict[str, Any]:
    """The columns of a Maps run: the core place facts, a score, and whatever extras the request asked for."""
    cfg = intent.places or {}
    columns = [c for c, _ in CORE_COLUMNS]
    labels = [label for _, label in CORE_COLUMNS]
    for extra in cfg.get("extra_fields") or []:
        if extra in EXTRA_COLUMNS:
            col, label = EXTRA_COLUMNS[extra]
            columns.append(col)
            labels.append(label)
    if cfg.get("scrape_sites"):
        from places_sites import SITE_COLUMNS

        columns += [c for c, _ in SITE_COLUMNS]
        labels += [label for _, label in SITE_COLUMNS]
    # lead_score and the search that found the place close the table.
    columns += ["lead_score", "matched_query"]
    labels += ["Lead score" if cfg.get("lead_focus") else "Score", "Found by search"]
    what = "prospects" if cfg.get("lead_focus") else "places"
    return {"columns": columns, "column_labels": labels, "description": f"Google Maps {what} for: {intent.topic}"}
