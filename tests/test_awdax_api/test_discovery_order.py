"""The order discovery tries sources in: ranked websites first, section fallbacks, followed front pages, curated anchors, then searches."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import inspector  # noqa: E402
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


class DiscoveryOrderTests(unittest.TestCase):
    def test_research_sites_are_inspected_first_in_rank_order_then_anchors_then_searches(self):
        inspected = []

        def cand(hit, **kw):
            return SourceCandidate(url=hit["url"], title=hit.get("title") or "", domain="d", http_status=200, https_ok=True)

        def inspect(_intent, c):
            inspected.append(c.url)
            return ScrapePlan(source_name=c.url, entry_url=c.url, source_url=c.url, blocked=c.url.endswith("/blocked"), confidence=0.8)

        anchor = mock.Mock(url="https://anchor.test/a", title="Anchor", source_category="other")
        sites = [{"rank": i, "url": f"https://r{i}.test/{'blocked' if i == 2 else 'list'}", "site_name": f"R{i}"} for i in (1, 2, 3)]
        events = []
        with mock.patch.dict(os.environ, {"DISCOVERY_INSPECT_WORKERS": "1", "DISCOVERY_MAX_SOURCES": "4"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[anchor]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("source_search.search_hits_for_query", side_effect=lambda q, *a, **k: [{"url": f"https://search.test/{q}"}]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand) as built, \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source", side_effect=inspect):
            sources, plans = discover_inspected_from_queries(_intent(), [GeneratedQuery(query="q1")], research_sites=sites, on_source=events.append)
        self.assertEqual(inspected, ["https://r1.test/list", "https://r2.test/blocked", "https://r3.test/list", "https://anchor.test/a", "https://search.test/q1"])
        self.assertEqual([p.origin for p in plans], ["research", "research", "anchor", "search"])
        self.assertEqual([e["origin"] for e in events if e["status"] != "inspecting"][:2], ["research", "research"])
        research_calls = [c for c in built.call_args_list if c.kwargs.get("stage") == "research"]
        self.assertEqual(len(research_calls), 3, "every research site gets its plain request, recorded under the research step")
        self.assertTrue(all(c.kwargs.get("job_id") == "job-r" for c in built.call_args_list))

    def test_a_research_link_that_does_not_exist_falls_back_to_a_cited_page_on_the_same_site(self):
        def cand(hit, **kw):
            gone = hit["url"].endswith("/debates")
            return SourceCandidate(url=hit["url"], domain="sansad.in", http_status=404 if gone else 200, https_ok=not gone)

        inspected = []
        site = {"rank": 1, "url": "https://sansad.in/ls/debates", "alt_urls": ["https://sansad.in/ls/debates/digitized"]}
        with mock.patch.dict(os.environ, {"DISCOVERY_MAX_SOURCES": "1"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand) as built, \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source", side_effect=lambda i, c: inspected.append(c.url) or ScrapePlan(source_name="s", entry_url=c.url, source_url=c.url)):
            _, plans = discover_inspected_from_queries(_intent(), [], research_sites=[site])
        self.assertEqual(inspected, ["https://sansad.in/ls/debates/digitized"])
        self.assertEqual([c.args[0]["url"] for c in built.call_args_list], ["https://sansad.in/ls/debates", "https://sansad.in/ls/debates/digitized"])
        self.assertEqual(len(plans), 1)

    def test_searching_stops_at_the_time_budget_once_a_source_is_accepted(self):
        def cand(hit, **kw):
            return SourceCandidate(url=hit["url"], domain="d", http_status=200, https_ok=True)

        with mock.patch.dict(os.environ, {"DISCOVERY_MAX_SOURCES": "6", "DISCOVERY_MAX_SECONDS": "0", "DISCOVERY_INSPECT_WORKERS": "1"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("source_search.search_hits_for_query", side_effect=lambda q, *a, **k: [{"url": f"https://s.test/{q}"}]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand), \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source", side_effect=lambda i, c: ScrapePlan(source_name="s", entry_url=c.url, source_url=c.url)) as inspect:
            _, plans = discover_inspected_from_queries(_intent(), [GeneratedQuery(query=f"q{i}") for i in range(5)], research_sites=[{"rank": 1, "url": "https://r.test/a"}])
        self.assertEqual(len(plans), 1, "the research site was accepted, so no search runs past the budget")
        self.assertEqual(inspect.call_count, 1)

    def test_a_research_page_that_does_not_exist_is_not_opened_in_a_browser(self):
        def cand(hit, **kw):
            return SourceCandidate(url=hit["url"], domain="d", http_status=404, https_ok=False)

        with mock.patch.dict(os.environ, {"DISCOVERY_MAX_SOURCES": "2"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("source_search.search_hits_for_query", return_value=[]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand), \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source") as inspect:
            _, plans = discover_inspected_from_queries(_intent(), [], research_sites=[{"rank": 1, "url": "https://gone.test/x"}])
        inspect.assert_not_called()
        self.assertEqual(plans, [])


class HubFollowTests(unittest.TestCase):
    HUB = """<a href="/ls/debates/digitized">Debate Search</a> <a href="/ls/debates/introduction">Introduction</a>
    <a href="https://other.test/x">Elsewhere</a> <a href="#top">Top</a> <a href="/ls/login"><span>Login</span></a>"""

    def test_same_site_links_with_their_words(self):
        links = inspector.same_site_links(self.HUB, "https://sansad.test/ls/debates/introduction")
        self.assertEqual(links, [
            {"url": "https://sansad.test/ls/debates/digitized", "text": "Debate Search"},
            {"url": "https://sansad.test/ls/login", "text": "Login"},
        ])

    def test_the_model_picks_the_links_toward_the_records_and_words_decide_when_it_is_down(self):
        links = inspector.same_site_links(self.HUB, "https://sansad.test/ls/debates/introduction")
        with mock.patch.object(inspector, "gemini_json", return_value={"picks": [0, 9]}) as ask:
            self.assertEqual(inspector.links_toward_records(_intent(), "https://sansad.test/ls/debates/introduction", links), ["https://sansad.test/ls/debates/digitized"])
        self.assertIn("give me parliamentary debates", ask.call_args.args[0])
        with mock.patch.object(inspector, "gemini_json", side_effect=RuntimeError("down")):
            self.assertEqual(inspector.links_toward_records(_intent(), "u", links), ["https://sansad.test/ls/debates/digitized"])
        self.assertEqual(inspector.links_toward_records(_intent(), "u", []), [])

    def test_a_rejected_research_page_is_followed_before_the_next_ranked_site(self):
        inspected = []

        def cand(hit, **kw):
            return SourceCandidate(url=hit["url"], domain="d", http_status=200, https_ok=True)

        def inspect(_i, c):
            inspected.append(c.url)
            hub = c.url.endswith("/introduction")
            plan = ScrapePlan(source_name=c.url, entry_url=c.url, source_url=c.url, blocked=hub, confidence=0.8)
            plan.page_links = [{"url": "https://s.test/ls/debates/digitized", "text": "Debate Search"}] if hub else []
            return plan

        sites = [{"rank": 1, "url": "https://s.test/ls/debates/introduction", "site_name": "LS"}, {"rank": 2, "url": "https://r.test/list", "site_name": "RS"}]
        with mock.patch.dict(os.environ, {"DISCOVERY_INSPECT_WORKERS": "1", "DISCOVERY_MAX_SOURCES": "3"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand), \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch.object(inspector, "links_toward_records", return_value=["https://s.test/ls/debates/digitized"]) as pick, \
                mock.patch("inspector.inspect_source", side_effect=inspect):
            _, plans = discover_inspected_from_queries(_intent(), [], research_sites=sites)
        self.assertEqual(inspected, ["https://s.test/ls/debates/introduction", "https://s.test/ls/debates/digitized", "https://r.test/list"])
        self.assertEqual([p.source_url for p in plans], ["https://s.test/ls/debates/digitized", "https://r.test/list"])
        self.assertEqual(pick.call_count, 1, "a followed page is not followed again")
        self.assertTrue(all(p.page_links == [] for p in plans), "links are not saved with the chat")

    def test_a_javascript_page_is_counted_from_its_own_probe_not_by_opening_it_again(self):
        feed = {"total": 6923, "records": [{"a": "1", "b": "2"}]}
        self.assertEqual(inspector.rendered_row_count({"feed": feed}), 6923)
        self.assertEqual(inspector.rendered_row_count({"feed": {"records": [{}, {}]}}), 2)
        table = "<table>" + "<tr><th>Name</th><th>Year</th></tr>" + "<tr><td>IIT Bombay</td><td>1958</td></tr>" * 23 + "</table>"
        self.assertEqual(inspector.rendered_row_count({"rendered_html": table}), 23)
        self.assertEqual(inspector.rendered_row_count({"rendered_html": "<p>an article</p>"}), 0)
        self.assertEqual(inspector.rendered_row_count({}), 0)


class SectionFallbackTests(unittest.TestCase):
    def test_a_failed_plan_still_keeps_the_pages_links_for_following(self):
        signals = {"tables": [], "hard_blocked": False, "links": [{"url": "https://s.test/ls/debates/digitized", "text": "Debate Search"}]}
        with mock.patch.object(inspector, "probe_https", return_value={"https_ok": True, "http_status": 200, "final_url": "https://s.test/ls"}),                 mock.patch.object(inspector.url_access, "record_probe"),                 mock.patch.object(inspector, "_probe_page_selenium", return_value=signals),                 mock.patch.object(inspector, "gemini_json", return_value="not a plan") as ask:
            plan = inspector.inspect_source(_intent(), SourceCandidate(url="https://s.test/ls", domain="s.test"))
        self.assertTrue(plan.blocked)
        self.assertEqual(ask.call_count, 2, "a malformed answer is asked once more")
        self.assertEqual(plan.page_links, signals["links"])
        with mock.patch.object(inspector, "gemini_json", return_value=[{"source_name": "LS", "holds_requested_records": True}]):
            self.assertEqual(inspector._plan_from_gemini(_intent(), SourceCandidate(url="https://s.test", domain="s"), {}).source_name, "LS")

    def test_parent_pages_nearest_first(self):
        self.assertEqual(inspector.parent_pages("https://s.test/ls/debates/x?y=1"), ["https://s.test/ls/debates", "https://s.test/ls", "https://s.test/"])
        self.assertEqual(inspector.parent_pages("https://s.test/"), [])

    def test_a_ranked_page_that_does_not_exist_falls_back_to_its_section(self):
        tried = []

        def cand(hit, **kw):
            tried.append(hit["url"])
            exists = hit["url"] == "https://s.test/ls"
            return SourceCandidate(url=hit["url"], domain="s.test", http_status=200 if exists else 404, https_ok=exists)

        with mock.patch.dict(os.environ, {"DISCOVERY_MAX_SOURCES": "1"}), \
                mock.patch("listing_sources.anchor_listings_for_intent", return_value=[]), \
                mock.patch("query_generation.discovery_extra_queries", return_value=[]), \
                mock.patch("discovery.candidate_from_serp_hit", side_effect=cand), \
                mock.patch("table_merge.intent_avoid_oem_sites", return_value=False), \
                mock.patch("inspector.inspect_source", side_effect=lambda i, c: ScrapePlan(source_name="s", entry_url=c.url, source_url=c.url)):
            _, plans = discover_inspected_from_queries(_intent(), [], research_sites=[{"rank": 1, "url": "https://s.test/ls/debates"}])
        self.assertEqual(tried, ["https://s.test/ls/debates", "https://s.test/ls"])
        self.assertEqual([p.source_url for p in plans], ["https://s.test/ls"])

    def test_the_probe_waits_until_the_page_stops_filling_in(self):
        sizes = iter([0, 500, 4000, 4000, 4000, 4000])
        driver = mock.Mock(execute_script=mock.Mock(side_effect=lambda _js: next(sizes)))
        with mock.patch.object(inspector.time, "sleep") as sleep:
            inspector.wait_until_settled(driver, max_s=12, min_s=2)
        self.assertEqual(driver.execute_script.call_count, 5, "stops once the text stayed the same twice")
        self.assertLess(sum(c.args[0] for c in sleep.call_args_list), 12)


class AnchorListingTests(unittest.TestCase):
    def test_the_parliament_anchors_are_the_real_listing_pages_and_only_for_parliament_requests(self):
        import listing_sources

        parliament = listing_sources.anchor_listings_for_intent(_intent())
        self.assertEqual([a.url for a in parliament], [
            "https://sansad.in/ls/debates/digitized", "https://sansad.in/rs/debates/officials", "https://prsindia.org/sessiontrack",
        ])
        self.assertTrue(all(a.url.startswith("https://") for a in parliament))
        self.assertEqual(len({a.url for a in parliament}), len(parliament))
        flights = ScrapeIntent(job_id="j", topic="flights", raw_prompt="cheapest flights from delhi to goa")
        self.assertEqual(listing_sources.anchor_listings_for_intent(flights), [], "no other request gets them")
        evs = ScrapeIntent(job_id="j", topic="electric cars", raw_prompt="list all electric cars in India")
        self.assertTrue(all("Electric_car_use_in_India" not in a.url for a in listing_sources.anchor_listings_for_intent(evs)))

    def test_an_indian_parliament_request_is_recognised_from_plain_words_but_another_countrys_is_not(self):
        from regulatory_strategy import intent_is_parliament_sessions

        def intent(prompt):
            return ScrapeIntent(job_id="j", topic=prompt, raw_prompt=prompt)

        for prompt in ("give me parliamentary debates in india between 2010 to 2025", "list of all debates that happened in indian parliament in last 5 years",
                       "debates in the Indian parliament about farm laws", "lok sabha sessions list"):
            self.assertTrue(intent_is_parliament_sessions(intent(prompt)), prompt)
        for prompt in ("UK parliament hansard debates 2020", "parliamentary debates in canada", "debate competitions in india", "list all the IITs in India"):
            self.assertFalse(intent_is_parliament_sessions(intent(prompt)), prompt)

    def test_the_extra_search_seeds_name_the_real_sections(self):
        from query_generation import discovery_extra_queries

        seeds = [q.query for q in discovery_extra_queries(_intent(), existing=set())]
        self.assertIn("site:sansad.in/ls/debates Lok Sabha debates search", seeds)
        self.assertFalse([s for s in seeds if "wikipedia" in s.lower()], "the Wikipedia session pages those seeds chased do not exist")


if __name__ == "__main__":
    unittest.main()
