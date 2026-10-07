"""Inspecting a source: one browser visit, relevance judged from the user's words, JavaScript pages read after rendering."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import inspector  # noqa: E402
import listing_extract  # noqa: E402
import url_access  # noqa: E402
from discovery import SourceCandidate  # noqa: E402
from inspector import ScrapePlan, discover_inspected_from_queries  # noqa: E402
from query_generation import GeneratedQuery  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402


def _intent(prompt="give me parliamentary debates in india between 2010 to 2025"):
    return ScrapeIntent(job_id="job-r", topic="Indian parliamentary debates", raw_prompt=prompt, geography="India")


def _rest_answer(text, chunks=(), queries=()):
    return {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "groundingMetadata": {"webSearchQueries": list(queries), "groundingChunks": [{"web": {"title": t, "uri": u}} for t, u in chunks]},
        }]
    }


class RelevanceTests(unittest.TestCase):
    def test_the_real_reason_for_a_rejection_is_listed_first(self):
        plan = ScrapePlan(source_name="W", entry_url="https://w.test", off_topic=True, warnings=["The page is an SPA"])
        inspector._finalize_inspection_plan(plan, https_probe={"http_status": 200, "https_ok": True}, signals={})
        self.assertTrue(plan.blocked)
        self.assertIn("does not list the records", plan.warnings[0])
        self.assertEqual(plan.warnings[1:], ["The page is an SPA"])

    def test_a_page_about_the_topic_without_the_records_is_rejected(self):
        plan = ScrapePlan(source_name="Wikipedia: Lok Sabha", entry_url="https://w.test", dry_run_rows=18, off_topic=True)
        reason = inspector.inspection_reject_reason(plan, https_probe={"http_status": 200, "https_ok": True}, signals={})
        self.assertIn("does not list the records", reason)
        plan.off_topic = False
        self.assertIsNone(inspector.inspection_reject_reason(plan, https_probe={"http_status": 200, "https_ok": True}, signals={}))

    def test_the_inspecting_model_is_asked_with_the_users_own_words(self):
        answer = {"source_name": "W", "holds_requested_records": False, "confidence": 0.7}
        with mock.patch.object(inspector, "gemini_json", return_value=answer) as ask:
            plan = inspector._plan_from_gemini(_intent(), SourceCandidate(url="https://w.test", domain="w.test"), {})
        self.assertTrue(plan.off_topic)
        self.assertIn("give me parliamentary debates in india between 2010 to 2025", ask.call_args.args[0])
        self.assertTrue(ScrapePlan.from_dict(plan.to_dict()).off_topic, "kept when the plan is saved and read back")


class JavaScriptShellTests(unittest.TestCase):
    SHELL = "<html><head>" + '<script src="/_next/app.js"></script>' * 10 + '<script id="__NEXT_DATA__">' + "{\"rows\": [1]}" * 4000 + "</script></head><body><div id=\"__next\">Loading</div></body></html>"
    PAGE = "<html><body><table>" + "<tr><td>Need to enhance the potential of National Waterways</td><td>2025-02-04</td></tr>" * 80 + "</table></body></html>"

    def test_an_app_shell_needs_the_browser_and_a_real_page_does_not(self):
        self.assertTrue(listing_extract.needs_browser(self.SHELL))
        self.assertFalse(listing_extract.needs_browser(self.PAGE))
        self.assertFalse(listing_extract.needs_browser("<p>small</p>"))

    def test_a_shell_is_rendered_before_the_model_reads_it(self):
        driver = mock.Mock(page_source=self.PAGE)
        runner = mock.Mock(driver=driver)
        plan = ScrapePlan(source_name="LS", entry_url="https://s.test/debates")
        with mock.patch.object(listing_extract, "fetch_html", return_value={"html": self.SHELL, "http_status": 200, "https_ok": True}), \
                mock.patch.object(listing_extract, "PlanDrivenScraper", return_value=runner), \
                mock.patch.object(url_access, "record_failure") as record:
            html = listing_extract._fetch_html_for_gemini(plan, "https://s.test/debates", scroll_listing=False, job_id="j")
        self.assertEqual(html, self.PAGE)
        runner.open_entry.assert_called_once()
        runner.quit.assert_called_once()
        record.assert_not_called()

    def test_placeholder_data_in_the_shell_is_not_read_after_rendering(self):
        fake = '<script id="__NEXT_DATA__" type="application/json">{"rows": [{"title": "Starred questions", "url": "http://www.africau.edu/sample.pdf"}]}</script>'
        ld = '<script type="application/ld+json">{"@type": "Dataset"}</script>'
        rendered = "<html><head>" + fake + ld + "</head>" + self.PAGE[6:]
        runner = mock.Mock(driver=mock.Mock(page_source=rendered))
        with mock.patch.object(listing_extract, "fetch_html", return_value={"html": self.SHELL, "http_status": 200, "https_ok": True}), \
                mock.patch.object(listing_extract, "PlanDrivenScraper", return_value=runner):
            html = listing_extract._fetch_html_for_gemini(ScrapePlan(source_name="LS", entry_url="u"), "https://s.test", scroll_listing=False)
        self.assertNotIn("africau", html)
        self.assertIn("National Waterways", html)
        self.assertIn("application/ld+json", html, "structured data the page publishes on purpose is kept")

    def test_a_plain_page_is_read_without_a_browser_and_a_refused_one_is_recorded(self):
        with mock.patch.object(listing_extract, "fetch_html", return_value={"html": self.PAGE, "http_status": 200, "https_ok": True}), \
                mock.patch.object(listing_extract, "PlanDrivenScraper") as browser:
            self.assertEqual(listing_extract._fetch_html_for_gemini(ScrapePlan(source_name="x", entry_url="u"), "https://s.test", scroll_listing=False), self.PAGE)
        browser.assert_not_called()
        with mock.patch.object(listing_extract, "fetch_html", return_value={"html": "", "http_status": 403, "https_ok": False}), \
                mock.patch.object(url_access, "record_failure") as record:
            listing_extract._fetch_html_for_gemini(ScrapePlan(source_name="x", entry_url="u"), "https://s.test", scroll_listing=False, job_id="j")
        self.assertEqual(record.call_args.kwargs["outcome"], "blocked")
        self.assertEqual(record.call_args.kwargs["stage"], "scrape")


class SingleBrowserInspectionTests(unittest.TestCase):
    """Inspecting a source opens one browser: the probe's page, tables, links and data feed answer everything."""

    def inspect(self, signals, answer, intent=None):
        probe = {"https_ok": True, "http_status": 200, "final_url": "https://s.test/ls/debates", "table_count": 0, "table_headers_preview": []}
        with mock.patch.object(inspector, "probe_https", return_value=probe), mock.patch.object(inspector.url_access, "record_probe"), \
                mock.patch.object(inspector, "_probe_page_selenium", return_value=signals) as browser, \
                mock.patch.object(inspector, "dry_run_plan") as dry, mock.patch.object(inspector, "_apply_ai_column_map") as colmap, \
                mock.patch.object(inspector, "gemini_json", return_value=answer), mock.patch.object(inspector, "llm_listing_estimate", return_value=0) as listing:
            plan = inspector.inspect_source(intent or _intent(), SourceCandidate(url="https://s.test/ls/debates", domain="s.test"))
        return plan, browser, dry, colmap, listing

    def test_the_feed_found_by_the_probe_is_the_listing_and_nothing_else_opens_a_browser(self):
        signals = {"tables": [], "hard_blocked": False, "rendered_html": "<p>" + "rows " * 100 + "</p>",
                   "feed": {"url": "https://api.test/q?page=1", "total": 6923, "records": [{"a": "x", "b": "y"}], "params": [["page", "1"]]}}
        plan, browser, dry, colmap, listing = self.inspect(signals, {"source_name": "LS", "holds_requested_records": True})
        self.assertFalse(plan.blocked)
        self.assertEqual(plan.dry_run_rows, 20)
        self.assertEqual(plan.feed["total"], 6923)
        browser.assert_called_once()
        dry.assert_not_called()
        colmap.assert_not_called()
        listing.assert_not_called()
        self.assertEqual(inspector.ScrapePlan.from_dict(plan.to_dict()).feed["total"], 6923, "kept when the plan is saved")

    def test_the_plan_prompt_gets_a_compact_view_not_the_pages_html(self):
        html = "<html><body><p>" + "visible words " * 400 + "</p>" + "<div>filler</div>" * 5000 + "</body></html>"
        signals = {"tables": [], "hard_blocked": False, "rendered_html": html, "links": [{"url": f"https://s.test/{i}", "text": f"link {i}"} for i in range(200)],
                   "feed": {"total": 5, "records": [{"a": "x"}]}, "https_probe": {"http_status": 200, "dataset_links": ["https://s.test/f.csv"]}}
        view = inspector._signals_for_prompt(signals)
        self.assertNotIn("rendered_html", view)
        self.assertLess(len(json.dumps(view)), 8000)
        self.assertEqual(len(view["links_sample"]), 25)
        self.assertEqual(view["data_feed"]["records_total"], 5)
        self.assertNotIn("dataset_links", view["https_probe"])

    def test_only_the_egazette_plan_still_uses_the_selenium_scraper(self):
        self.assertTrue(inspector._uses_selenium_scraper(ScrapePlan(source_name="g", entry_url="https://egazette.gov.in/x")))
        self.assertTrue(inspector._uses_selenium_scraper(ScrapePlan(source_name="g", entry_url="https://x.test", table_selector="#gvGazetteList")))
        self.assertFalse(inspector._uses_selenium_scraper(ScrapePlan(source_name="s", entry_url="https://sansad.in/ls")))

    def test_a_feed_is_read_again_without_a_browser_and_round_trips(self):
        import data_feed

        feed = data_feed.Feed(url="https://api.test/q?page=1&size=10", path=["records"], records=[{"d": "30/07/2026", "t": "x"}] * 30, total=99,
                              params=[("page", "1"), ("size", "10")], page_key="page", size_key="size", size=10)
        again = data_feed.Feed.from_dict(json.loads(json.dumps(feed.to_dict())))
        self.assertEqual((again.url, again.path, again.total, again.page_key, again.size_key, again.size), (feed.url, feed.path, 99, "page", "size", 10))
        self.assertEqual(len(again.records), 20)
        with mock.patch.object(data_feed, "capture_json") as capture, mock.patch.object(data_feed, "_fetch_json", return_value={"records": [{"d": "01/02/2020", "t": "p"}]}), \
                mock.patch.object(data_feed, "column_mapping", return_value={"title": ["t"]}):
            rows = data_feed.read_feed("https://s.test", goal="g", columns=["title"], labels=["Title"], max_rows=5, feed=again)
        capture.assert_not_called()
        self.assertEqual(rows[0], {"title": "p"})

    def test_searches_stop_once_enough_sources_are_accepted(self):
        def cand(hit, **kw):
            return SourceCandidate(url=hit["url"], domain="d", http_status=200, https_ok=True)

        sites = [{"rank": i, "url": f"https://r{i}.test/list"} for i in range(1, 5)]
        with mock.patch.dict(os.environ, {"DISCOVERY_MAX_SOURCES": "6", "DISCOVERY_ENOUGH_SOURCES": "4", "DISCOVERY_INSPECT_WORKERS": "1"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("source_search.search_hits_for_query", return_value=[{"url": "https://search.test/a"}]) as search, \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand), \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source", side_effect=lambda i, c: ScrapePlan(source_name="s", entry_url=c.url, source_url=c.url)):
            _, plans = discover_inspected_from_queries(_intent(), [GeneratedQuery(query="q1")], research_sites=sites)
        self.assertEqual(len(plans), 4)
        search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
