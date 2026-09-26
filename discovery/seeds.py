"""High-confidence seed URLs by topic (used when search is noisy)."""

from __future__ import annotations

import re

_EV_INDIA = re.compile(
    r"\b(ev|electric|vehicle|car|scooter)\b.*\b(india|indian)\b"
    r"|\b(india|indian)\b.*\b(ev|electric|vehicle|car|scooter)\b",
    re.I,
)


def topic_seed_urls(user_goal: str) -> list[str]:
    goal = user_goal.strip()
    if _EV_INDIA.search(goal):
        return [
            "https://www.cardekho.com/electric-cars",
            "https://www.carwale.com/electric-cars/",
            "https://www.zigwheels.com/electric-cars",
            "https://www.autocarindia.com/car-finder/electric-cars",
            "https://www.cardekho.com/newcars/electric",
        ]
    return []
