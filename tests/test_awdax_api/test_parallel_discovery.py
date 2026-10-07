"""Discovery inspects several sources at once (DISCOVERY_INSPECT_WORKERS) without changing what it returns."""

import os
import threading
import time
import unittest
from unittest.mock import patch

from discovery import SourceCandidate
from inspector import ScrapePlan, discover_inspected_from_queries
from query_generation import GeneratedQuery
from reasoning import ScrapeIntent


def _cand(hit, **_kw):
    url = hit["url"]
    return SourceCandidate(url=url, title=url.rsplit("/", 1)[-1], domain="example.org")


def _plan(url, *, blocked=False):
    return ScrapePlan(source_name=url, entry_url=url, source_url=url, blocked=blocked, confidence=0.0 if blocked else 0.8)


class ParallelDiscoveryTests(unittest.TestCase):
    def run_discovery(self, queries, *, inspect, hits=None, env=None, on_source=None, on_progress=None):
        hits = hits or (lambda q, *_a, **_k: [{"url": f"https://example.org/{q}"}])
        with (
            patch.dict(os.environ, env or {}),
            patch("listing_sources.anchor_listings_for_intent", return_value=[]),
            # A fixed query list: the extra queries that chase the source target are test_discovery_target's subject.
            patch("query_generation.discovery_extra_queries", return_value=[]),
            patch("source_search.search_hits_for_query", side_effect=hits),
            patch("discovery.candidate_from_serp_hit", side_effect=_cand),
            patch("table_merge.intent_avoid_oem_sites", return_value=False),
            patch("inspector.inspect_source", side_effect=inspect),
        ):
            return discover_inspected_from_queries(
                ScrapeIntent.from_dict({"topic": "cars"}),
                [GeneratedQuery(query=q) for q in queries],
                on_source=on_source,
                on_progress=on_progress,
            )

    def test_inspections_overlap_and_keep_query_order(self):
        # Overlap measured directly (how many inspections run at once), not by wall time, so a busy machine can't flake it.
        lock = threading.Lock()
        running = [0]
        peak = [0]

        def slow(_intent, cand):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.2)
            with lock:
                running[0] -= 1
            return _plan(cand.url)

        sources, plans = self.run_discovery([f"q{i}" for i in range(6)], inspect=slow, env={"DISCOVERY_INSPECT_WORKERS": "3", "DISCOVERY_MAX_SOURCES": "6", "DISCOVERY_ENOUGH_SOURCES": "6"})
        self.assertEqual([p.source_url for p in plans], [f"https://example.org/q{i}" for i in range(6)])
        self.assertEqual(len(sources), 6)
        self.assertEqual(peak[0], 3)

    def test_cap_is_respected_without_extra_inspections(self):
        calls = []

        def inspect(_intent, cand):
            calls.append(cand.url)
            return _plan(cand.url)

        _sources, plans = self.run_discovery([f"q{i}" for i in range(10)], inspect=inspect, env={"DISCOVERY_INSPECT_WORKERS": "3", "DISCOVERY_MAX_SOURCES": "4"})
        self.assertEqual(len(plans), 4)
        self.assertEqual(len(calls), 4)

    def test_blocked_sources_are_skipped_and_later_queries_fill_the_cap(self):
        def inspect(_intent, cand):
            return _plan(cand.url, blocked=cand.url.endswith("q1"))

        _sources, plans = self.run_discovery([f"q{i}" for i in range(5)], inspect=inspect, env={"DISCOVERY_INSPECT_WORKERS": "2", "DISCOVERY_MAX_SOURCES": "5"})
        self.assertEqual([p.source_url.rsplit("/", 1)[-1] for p in plans], ["q0", "q2", "q3", "q4"])

    def test_a_rejected_page_moves_on_to_the_next_hit_of_its_query(self):
        hits = lambda q, *_a, **_k: [{"url": f"https://example.org/{q}-dead"}, {"url": f"https://example.org/{q}-ok"}]  # noqa: E731
        _sources, plans = self.run_discovery(
            ["q0", "q1"],
            inspect=lambda _i, cand: _plan(cand.url, blocked=cand.url.endswith("-dead")),
            hits=hits,
            env={"DISCOVERY_INSPECT_WORKERS": "2", "DISCOVERY_MAX_SOURCES": "2"},
        )
        self.assertEqual([p.source_url.rsplit("/", 1)[-1] for p in plans], ["q0-ok", "q1-ok"])

    def test_the_same_site_is_never_inspected_twice(self):
        calls = []

        def inspect(_intent, cand):
            calls.append(cand.url)
            return _plan(cand.url)

        same = lambda *_a, **_k: [{"url": "https://example.org/same"}]  # noqa: E731
        _sources, plans = self.run_discovery(["a", "b", "c"], inspect=inspect, hits=same, env={"DISCOVERY_INSPECT_WORKERS": "3", "DISCOVERY_MAX_SOURCES": "3"})
        self.assertEqual(calls, ["https://example.org/same"])
        self.assertEqual(len(plans), 1)

    def test_a_failing_search_loses_only_its_own_query(self):
        def hits(q, *_a, **_k):
            if q == "q1":
                raise RuntimeError("search API down")
            return [{"url": f"https://example.org/{q}"}]

        progress = []
        _sources, plans = self.run_discovery(
            ["q0", "q1", "q2"],
            inspect=lambda _i, cand: _plan(cand.url),
            hits=hits,
            env={"DISCOVERY_INSPECT_WORKERS": "3", "DISCOVERY_MAX_SOURCES": "3"},
            on_progress=progress.append,
        )
        self.assertEqual([p.source_url.rsplit("/", 1)[-1] for p in plans], ["q0", "q2"])
        self.assertTrue(any("q1" in m and "failed" in m for m in progress), progress)

    def test_a_fast_site_is_validated_before_the_slow_one_in_its_wave_finishes(self):
        # Deterministic, not timed: the slow inspection only finishes once the fast site's "validated" update has
        # reached the caller. If updates waited for the whole wave, the slow worker would time out instead.
        fast_seen = threading.Event()
        slow_timed_out = []
        order = []

        def inspect(_intent, cand):
            if cand.url.endswith("slow"):
                slow_timed_out.append(not fast_seen.wait(timeout=5))
            return _plan(cand.url)

        def on_source(item):
            if item["status"] == "validated":
                name = item["url"].rsplit("/", 1)[-1]
                order.append(name)
                if name == "fast":
                    fast_seen.set()

        self.run_discovery(["slow", "fast"], inspect=inspect, env={"DISCOVERY_INSPECT_WORKERS": "2", "DISCOVERY_MAX_SOURCES": "2"}, on_source=on_source)
        self.assertEqual(slow_timed_out, [False])
        self.assertEqual(order, ["fast", "slow"])

    def test_callbacks_run_on_the_calling_thread(self):
        main = threading.get_ident()
        seen = set()
        statuses = []

        def on_source(item):
            seen.add(threading.get_ident())
            statuses.append(item["status"])

        self.run_discovery(
            ["q0", "q1", "q2"],
            inspect=lambda _i, cand: _plan(cand.url),
            env={"DISCOVERY_INSPECT_WORKERS": "3", "DISCOVERY_MAX_SOURCES": "3"},
            on_source=on_source,
            on_progress=lambda _m: seen.add(threading.get_ident()),
        )
        self.assertEqual(seen, {main})
        self.assertEqual(statuses.count("inspecting"), 3)
        self.assertEqual(statuses.count("validated"), 3)


if __name__ == "__main__":
    unittest.main()
