"""Routing: Parliament sessions must not use RegulatoryFeed / eGazette."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from reasoning import ScrapeIntent
from regulatory_strategy import enrich_intent_for_execution, intent_uses_regulatory_feed
from query_generation import generate_search_queries


class ParliamentRoutingTests(unittest.TestCase):
    def _misrouted_parliament_intent(self) -> ScrapeIntent:
        return ScrapeIntent.from_dict(
            {
                "job_id": "test",
                "topic": "Lok Sabha and Rajya Sabha parliamentary sessions",
                "geography": "India",
                "entity_types": ["Parliament Session", "Lok Sabha", "Rajya Sabha"],
                "output_fields": ["house_name", "session_number", "start_date", "end_date"],
                "freshness": "past 5 years",
                "named_sites": [
                    "https://sansad.in",
                    "https://loksabha.nic.in",
                    "https://rajyasabha.nic.in",
                    "https://egazette.gov.in",
                ],
                "constraints": [
                    "official sources only",
                    "official egazette.gov.in listing only",
                ],
                "max_sources": 1,
                "raw_prompt": "give me data about all session of rajya and lok sabh in past 5 years",
                "pipeline": "regulatory_feed",
            }
        )

    def test_parliament_prompt_not_regulatory_feed(self) -> None:
        intent = enrich_intent_for_execution(self._misrouted_parliament_intent())
        self.assertEqual(intent.pipeline, "universal")
        self.assertFalse(intent_uses_regulatory_feed(intent))
        self.assertTrue(all("egazette" not in s.lower() for s in intent.named_sites))
        self.assertGreaterEqual(intent.max_sources, 6)

    @patch(
        "query_generation.gemini_json",
        return_value=[
            {"query": "Lok Sabha session list past 5 years site:sansad.in"},
            {"query": "Rajya Sabha sessions dates loksabha.nic.in"},
        ],
    )
    def test_parliament_queries_not_egazette_site(self, _mock_gemini) -> None:
        intent = enrich_intent_for_execution(self._misrouted_parliament_intent())
        queries = generate_search_queries(intent, count=3)
        self.assertGreater(len(queries), 1)
        self.assertFalse(any("egazette.gov.in" in q.query for q in queries))

    def test_explicit_egazette_still_regulatory(self) -> None:
        intent = ScrapeIntent.from_dict(
            {
                "job_id": "eg",
                "topic": "Latest ministry notifications",
                "raw_prompt": "scrape latest egazette notifications from egazette.gov.in",
                "pipeline": "regulatory_feed",
                "named_sites": ["https://egazette.gov.in"],
                "max_sources": 1,
            }
        )
        intent = enrich_intent_for_execution(intent)
        self.assertTrue(intent_uses_regulatory_feed(intent))
        self.assertEqual(intent.pipeline, "regulatory_feed")


if __name__ == "__main__":
    unittest.main()
