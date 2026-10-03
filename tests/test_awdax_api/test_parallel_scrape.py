"""The scrape step fetches and extracts several sources at once (SCRAPE_WORKERS) while every database write stays on
the calling thread, in source order, so results are the same as one source at a time."""
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scraper  # noqa: E402
from inspector import ScrapePlan  # noqa: E402


def _plan(name, **kw):
    return ScrapePlan(source_name=name, entry_url=f"https://example.org/{name}", source_url=f"https://example.org/{name}", **kw)


class ParallelScrapeTests(unittest.TestCase):
    def setUp(self):
        self.svc = scraper.UniversalScrapeService()
        for name in ("save_job", "_set_status", "emit_event"):
            p = mock.patch.object(self.svc, name)
            p.start()
            self.addCleanup(p.stop)
        for name, value in (("rebuild_merged_table", {"row_count": 0}), ("_merged_row_keys", set()), ("get_job_status", {})):
            p = mock.patch.object(self.svc, name, return_value=value)
            p.start()
            self.addCleanup(p.stop)
        self.job = mock.Mock(job_id="job-1", table_schema={"columns": ["model"]})
        self.main = threading.get_ident()
        self.lock = threading.Lock()
        self.running = 0
        self.peak = 0
        self.stored = []

    def _listing(self, delay=0.15, fail=()):
        def listing_rows(plan, job):
            with self.lock:
                self.running += 1
                self.peak = max(self.peak, self.running)
            try:
                time.sleep(delay)
                if plan.source_name in fail:
                    raise RuntimeError(f"{plan.source_name} timed out")
                return [{"model": plan.source_name}]
            finally:
                with self.lock:
                    self.running -= 1
        return listing_rows

    def _store(self, plan, job, rows):
        self.stored.append((plan.source_name, threading.get_ident() == self.main))
        return len(rows)

    def run_all(self, plans, env, listing):
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(self.svc, "_listing_rows", side_effect=listing),
            mock.patch.object(self.svc, "_store_rows", side_effect=self._store),
        ):
            self.svc._run_all(plans, self.job, 1)

    def test_sources_are_fetched_at_once_and_stored_in_order_on_the_calling_thread(self):
        plans = [_plan(f"s{i}") for i in range(6)]
        self.run_all(plans, {"SCRAPE_WORKERS": "3"}, self._listing())
        self.assertEqual(self.peak, 3)
        self.assertEqual(self.stored, [(f"s{i}", True) for i in range(6)])
        self.assertEqual(self.job.status, "completed")

    def test_one_worker_is_the_old_one_at_a_time_scrape(self):
        self.run_all([_plan(f"s{i}") for i in range(3)], {"SCRAPE_WORKERS": "1"}, self._listing(delay=0.02))
        self.assertEqual(self.peak, 1)
        self.assertEqual([name for name, _ in self.stored], ["s0", "s1", "s2"])

    def test_a_failing_source_is_recorded_and_the_rest_still_stored(self):
        self.run_all([_plan("a"), _plan("b"), _plan("c")], {"SCRAPE_WORKERS": "3"}, self._listing(fail=("b",)))
        self.assertEqual([name for name, _ in self.stored], ["a", "c"])
        self.assertEqual(self.job.status, "partial")

    def test_selenium_and_blocked_plans_keep_the_sequential_path(self):
        calls = []

        def run_single(plan, job, max_pages):
            calls.append((plan.source_name, threading.get_ident() == self.main))
            return 0

        regulatory = _plan("gazette")
        plans = [_plan("a"), regulatory, _plan("blocked", blocked=True), _plan("b")]
        with (
            mock.patch.object(scraper, "_is_regulatory_table_plan", side_effect=lambda p: p is regulatory),
            mock.patch.object(self.svc, "_run_single", side_effect=run_single),
        ):
            self.run_all(plans, {"SCRAPE_WORKERS": "3"}, self._listing(delay=0.02))
        self.assertEqual(calls, [("gazette", True), ("blocked", True)])
        self.assertEqual([name for name, _ in self.stored], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
