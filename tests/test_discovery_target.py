"""Discovery should keep trying until multiple sources validate."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from discovery import SourceCandidate
from inspector import ScrapePlan, discover_inspected_from_queries
from query_generation import GeneratedQuery
from reasoning import ScrapeIntent


class DiscoveryTargetTests(unittest.TestCase):
    @patch("listing_sources.anchor_listings_for_intent", return_value=[])
    @patch("table_merge.intent_avoid_oem_sites", return_value=False)
    def test_keeps_searching_until_target(self, _oem, _anchors) -> None:
        urls = [
            "https://example.org/a",
            "https://example.org/b",
            "https://example.org/c",
        ]
        calls = {"i": 0}

        def next_hit(_query, _intent, exclude_urls=None):
            i = calls["i"]
            calls["i"] += 1
            if i >= len(urls):
                return []
            return [{"url": urls[i], "title": f"Site {i}"}]

        def make_cand(hit, **kwargs):
            return SourceCandidate(url=hit["url"], title=hit["title"], domain="example.org")

        def inspect(_intent, cand):
            if cand.url.endswith("/a"):
                return ScrapePlan(
                    source_name="A",
                    entry_url=cand.url,
                    source_url=cand.url,
                    blocked=True,
                    warnings=["HTTP 404"],
                )
            return ScrapePlan(
                source_name=cand.title,
                entry_url=cand.url,
                source_url=cand.url,
                dry_run_rows=3,
                confidence=0.7,
            )

        intent = ScrapeIntent.from_dict(
            {
                "topic": "Lok Sabha sessions",
                "raw_prompt": "lok sabha sessions list",
                "max_sources": 3,
            }
        )
        with (
            patch("source_search.search_hits_for_query", side_effect=next_hit),
            patch("discovery.candidate_from_serp_hit", side_effect=make_cand),
            patch("inspector.inspect_source", side_effect=inspect),
        ):
            sources, plans = discover_inspected_from_queries(
                intent,
                [GeneratedQuery(query="q1"), GeneratedQuery(query="q2"), GeneratedQuery(query="q3")],
            )
        self.assertEqual(len(plans), 2)
        self.assertEqual(len(sources), 2)


if __name__ == "__main__":
    unittest.main()
