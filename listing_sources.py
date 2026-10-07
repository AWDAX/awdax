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


# Tried only for requests about the Indian Parliament (intent_is_parliament_sessions), first, ahead of any search. Each address
# was checked to answer (HTTP 200) and to hold the records: the two official debate listings are JavaScript tables whose data
# feed is read page by page (data_feed.py); PRS's Session Track is the independent summary of every session. The earlier
# Wikipedia and PRS "sessions" addresses here had moved and answered 404 on every run.
_PARLIAMENT_ANCHORS: tuple[AnchorListing, ...] = (
    AnchorListing("Digital Sansad: Lok Sabha debates", "https://sansad.in/ls/debates/digitized", "government"),
    AnchorListing("Digital Sansad: Rajya Sabha official debates", "https://sansad.in/rs/debates/officials", "government"),
    AnchorListing("PRS Session Track", "https://prsindia.org/sessiontrack", "aggregator"),
)

_EV_INDIA_ANCHORS: tuple[AnchorListing, ...] = (
    AnchorListing("CarWale Electric Cars", "https://www.carwale.com/new/electric-cars/", "aggregator"),
    AnchorListing("CarDekho Electric Cars", "https://www.cardekho.com/electric-cars", "aggregator"),
    AnchorListing("91Wheels Electric Cars", "https://www.91wheels.com/electric-cars", "aggregator"),
    AnchorListing("ZigWheels Electric Cars", "https://www.zigwheels.com/newcars/electric-cars", "aggregator"),
    AnchorListing("Wikipedia EV industry in India", "https://en.wikipedia.org/wiki/Electric_vehicle_industry_in_India", "wiki"),
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
