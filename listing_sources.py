"""
Known exhaustive listing pages (aggregators / reference) for common scrape intents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from reasoning import ScrapeIntent
from regulatory_strategy import intent_is_parliament_sessions


@dataclass(frozen=True)
class AnchorListing:
    title: str
    url: str
    source_category: str = "aggregator"


_PARLIAMENT_ANCHORS: tuple[AnchorListing, ...] = (
    AnchorListing(
        "List of Lok Sabha sessions (Wikipedia)",
        "https://en.wikipedia.org/wiki/List_of_sessions_of_the_Lok_Sabha",
        "wiki",
    ),
    AnchorListing(
        "Rajya Sabha sessions (Wikipedia category)",
        "https://en.wikipedia.org/wiki/Category:Sessions_of_the_Rajya_Sabha",
        "wiki",
    ),
    AnchorListing(
        "PRS Parliament sessions",
        "https://prsindia.org/parliament-track/sessions",
        "aggregator",
    ),
)

_EV_INDIA_ANCHORS: tuple[AnchorListing, ...] = (
    AnchorListing("CarWale Electric Cars", "https://www.carwale.com/new/electric-cars/", "aggregator"),
    AnchorListing("CarDekho Electric Cars", "https://www.cardekho.com/electric-cars", "aggregator"),
    AnchorListing("91Wheels Electric Cars", "https://www.91wheels.com/electric-cars", "aggregator"),
    AnchorListing("ZigWheels Electric Cars", "https://www.zigwheels.com/newcars/electric-cars", "aggregator"),
    AnchorListing("Wikipedia EV India", "https://en.wikipedia.org/wiki/Electric_car_use_in_India", "wiki"),
)


def intent_wants_ev_catalog(intent: ScrapeIntent) -> bool:
    blob = " ".join([intent.topic, intent.raw_prompt, " ".join(intent.entity_types)]).lower()
    return bool(re.search(r"\bev\b|electric car|electric vehicle", blob))


def anchor_listings_for_intent(intent: ScrapeIntent) -> list[AnchorListing]:
    if intent_wants_ev_catalog(intent):
        return list(_EV_INDIA_ANCHORS)
    if intent_is_parliament_sessions(intent):
        return list(_PARLIAMENT_ANCHORS)
    return []


def is_aggregator_listing_url(url: str) -> bool:
    u = (url or "").lower()
    patterns = (
        "carwale.com/new/electric",
        "cardekho.com/electric",
        "91wheels.com/electric",
        "zigwheels.com/newcars/electric",
        "carwale.com/electric",
    )
    return any(p in u for p in patterns)
