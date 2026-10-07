"""The codebase audit: extraction, retrieval and merge fixes. Each test names a way the old code lost or invented data."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gemini_scrape  # noqa: E402
import inspector  # noqa: E402
import llm_client  # noqa: E402
import plan_scraper  # noqa: E402
import scraper  # noqa: E402
import table_merge  # noqa: E402
from inspector import ScrapePlan  # noqa: E402
from listing_extract import _finalize_extract_rows, extract_tables_from_html, find_next_page_url, table_to_text  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402


def _intent(prompt, topic=None, **kw):
    return ScrapeIntent(job_id="j", topic=topic or prompt, raw_prompt=prompt, **kw)


class TableReaderTests(unittest.TestCase):
    def test_a_row_that_starts_with_a_header_cell_is_data_and_empty_cells_keep_their_place(self):
        html = """<table><thead><tr><th>Name</th><th>City</th><th>Year</th></tr></thead><tbody>
        <tr><th scope=row>IIT Bombay</th><td>Mumbai</td><td>1958</td></tr>
        <tr><td>IIT Delhi</td><td></td><td>1961</td></tr></tbody></table>"""
        (table,) = extract_tables_from_html(html)
        self.assertEqual(table["headers"], ["Name", "City", "Year"])
        # the old reader dropped row 1 (it has a <th>) and slid "1961" under "City" in row 2
        self.assertEqual(table["rows"], [["IIT Bombay", "Mumbai", "1958"], ["IIT Delhi", "", "1961"]])

    def test_rowspan_and_colspan_keep_every_value_under_its_own_header(self):
        html = """<table><tr><th>Name</th><th>Area</th><th>Year</th></tr>
        <tr><td rowspan=2>IIT Madras</td><td>Chennai</td><td>1959</td></tr><tr><td>Guindy</td><td>1960</td></tr>
        <tr><td colspan=2>IIT Kanpur</td><td>1959</td></tr></table>"""
        (table,) = extract_tables_from_html(html)
        self.assertEqual(table["rows"], [["IIT Madras", "Chennai", "1959"], ["IIT Madras", "Guindy", "1960"], ["IIT Kanpur", "", "1959"]])

    def test_nested_tables_scripts_entities_and_line_breaks(self):
        html = """<table><tr><th>A</th><th>B</th></tr><tr><td>x<br>y</td><td><table><tr><td>inner</td></tr></table></td></tr>
        <tr><td>Tom &amp; Jerry</td><td><script>var t = "<td>no</td>"</script>ok</td></tr></table>"""
        tables = extract_tables_from_html(html)
        outer = max(tables, key=lambda t: len(t["headers"]))
        self.assertEqual(outer["rows"][0][0], "x y")
        self.assertEqual(outer["rows"][1], ["Tom & Jerry", "ok"])
        self.assertIn({"headers": [], "rows": [["inner"]]}, tables)

    def test_odd_html_never_raises(self):
        for html in ("", None, "no tables here", "<table><tr><td>unclosed", "<tr><td>orphan</td></tr>", "<table></table>", "<td>1<td>2<td>3"):
            self.assertIsInstance(extract_tables_from_html(html), list)
        self.assertEqual(extract_tables_from_html("<table><tr><td>unclosed")[0]["rows"], [["unclosed"]])

    def test_a_table_is_shown_as_compact_rows_within_a_budget(self):
        table = {"headers": ["Name", "City"], "rows": [[f"IIT {i}", "X"] for i in range(100)]}
        text, shown = table_to_text(table, max_chars=200)
        self.assertEqual(text.splitlines()[0], "Name | City")
        self.assertEqual(text.splitlines()[1], "IIT 0 | X")
        self.assertLess(shown, 100)
        self.assertLessEqual(len(text), 200)
        full, shown = table_to_text(table, max_chars=10_000)
        self.assertEqual((shown, len(full.splitlines())), (100, 101))
        self.assertEqual(table_to_text({"headers": [], "rows": [["a" * 500]]}, max_chars=900)[0], "a" * 160)


class PageDigestTests(unittest.TestCase):
    PAGE = "<html><body><h1>IITs</h1><table><tr><th>Name</th><th>Year</th></tr>" + "".join(f"<tr><td>IIT {i}</td><td>{1950 + i}</td></tr>" for i in range(30)) + "</table>" + "<p>filler </p>" * 5000 + "</body></html>"

    def test_the_tables_are_in_the_context_as_rows_and_the_text_is_shorter(self):
        digest = gemini_scrape.build_page_digest(self.PAGE)
        (table,) = digest["tables"]
        self.assertEqual((table["columns"], table["rows_shown"], table["rows_total"]), (["Name", "Year"], 30, 30))
        self.assertIn("IIT 17 | 1967", table["rows"])
        self.assertLessEqual(len(digest["visible_text_sample"]), 20_000)
        plain = gemini_scrape.build_page_digest("<html><body>" + "<p>filler </p>" * 5000 + "</body></html>")
        self.assertEqual(plain["tables"], [])
        self.assertGreater(len(plain["visible_text_sample"]), 20_000)

    def test_one_row_layout_tables_are_left_to_the_page_text(self):
        digest = gemini_scrape.build_page_digest("<table><tr><td>the whole page lives in this cell</td></tr></table>")
        self.assertEqual(digest["tables"], [])
        self.assertIn("the whole page lives in this cell", digest["visible_text_sample"])


class ExtractionTests(unittest.TestCase):
    def table_page(self, n):
        return "<html><body><table><tr><th>Name</th><th>City</th></tr>" + "".join(f"<tr><td>Place {i}</td><td>C{i}</td></tr>" for i in range(n)) + "</table>" + "<p>x</p>" * 100 + "</body></html>"

    def run_extract(self, html, answers):
        calls = []

        def fake(prompt, **kw):
            calls.append(prompt)
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with mock.patch.object(gemini_scrape, "gemini_json", side_effect=fake):
            rows = gemini_scrape.gemini_extract_rows_from_page(html, _intent("places"), ["name", "city"], page_url="https://x.test/")
        return rows, calls

    def test_a_short_table_is_one_call_and_the_model_sees_its_rows(self):
        rows, calls = self.run_extract(self.table_page(10), [{"rows": [{"name": "Place 3", "city": "C3"}]}])
        self.assertEqual(rows, [{"name": "Place 3", "city": "C3"}])
        self.assertEqual(len(calls), 1)
        self.assertIn("Place 9 | C9", calls[0])

    def test_a_long_table_is_read_in_parts_so_no_row_is_cut_off(self):
        answers = [{"rows": [{"name": f"P{n}-{i}", "city": "c"} for i in range(2)]} for n in range(3)]
        rows, calls = self.run_extract(self.table_page(150), answers)
        self.assertEqual(len(calls), 3)  # 150 rows in parts of 60
        self.assertEqual(len(rows), 6)
        self.assertIn("part 1 of 3", calls[0])
        self.assertIn("Place 0 | C0", calls[0])
        self.assertNotIn("Place 60 | C60", calls[0])
        self.assertIn("Place 149 | C149", calls[2])

    def test_a_part_that_fails_loses_only_its_own_rows(self):
        answers = [{"rows": [{"name": "A", "city": "1"}]}, RuntimeError("model busy"), {"rows": [{"name": "C", "city": "3"}]}]
        rows, _ = self.run_extract(self.table_page(150), answers)
        self.assertEqual([r["name"] for r in rows], ["A", "C"])

    def test_if_every_part_gives_nothing_the_whole_page_is_tried_once(self):
        rows, calls = self.run_extract(self.table_page(150), [{"rows": []}, {"rows": []}, {"rows": []}, {"rows": [{"name": "Z", "city": "z"}]}])
        self.assertEqual(rows, [{"name": "Z", "city": "z"}])
        self.assertEqual(len(calls), 4)

    def test_answers_are_cleaned_to_the_columns_asked_for(self):
        rows, _ = self.run_extract(self.table_page(5), [{"rows": [{"name": " X ", "city": None, "extra": "dropped"}, "junk", {"name": "", "city": ""}, {"name": "Y"}]}])
        self.assertEqual(rows, [{"name": "X", "city": ""}, {"name": "Y", "city": ""}])
        self.assertEqual(self.run_extract(self.table_page(5), [RuntimeError("down")])[0], [])
        self.assertEqual(self.run_extract("<html>tiny</html>", [])[0], [])

    def test_rows_without_a_name_column_get_a_stable_id_not_their_position(self):
        plan = ScrapePlan(source_name="s", entry_url="https://x.test/", id_field="id")
        first = _finalize_extract_rows([{"institute": "IIT Bombay", "city": "Mumbai"}, {"institute": "IIT Delhi", "city": "Delhi"}], plan, columns=["institute", "city"])
        second = _finalize_extract_rows([{"institute": "IIT Delhi", "city": "Delhi"}, {"institute": "IIT Bombay", "city": "Mumbai"}], plan, columns=["institute", "city"])
        ids = lambda rows: {r["institute"]: r["id"] for r in rows}  # noqa: E731
        self.assertEqual(ids(first), ids(second), "the same item keeps its id when the page order changes")
        self.assertEqual(ids(first)["IIT Bombay"], "IIT Bombay")


class SalvageTests(unittest.TestCase):
    def test_an_answer_cut_off_at_the_output_limit_keeps_its_complete_rows(self):
        cut = '{"rows": [{"name": "A", "n": 1}, {"name": "B", "n": 2}, {"name": "C", "n'
        self.assertEqual(llm_client._parse_json(cut), {"rows": [{"name": "A", "n": 1}, {"name": "B", "n": 2}]})
        self.assertEqual(llm_client._parse_json('[{"a": 1}, {"a": 2}, {"a'), [{"a": 1}, {"a": 2}])
        self.assertEqual(llm_client._parse_json('```json\n{"rows": [{"a": 1}, {"a": 2}\n'), {"rows": [{"a": 1}, {"a": 2}]})

    def test_complete_json_is_untouched_and_hopeless_text_still_fails(self):
        self.assertEqual(llm_client._parse_json('{"a": [1, 2]}'), {"a": [1, 2]})
        for bad in ("no json here", '{"a": "unterminated string', ""):
            with self.assertRaises(ValueError):
                llm_client._parse_json(bad)


class NextPageTests(unittest.TestCase):
    BASE = "https://shop.example.com/cars?page=2"

    def test_what_the_page_declares_wins(self):
        html = '<head><link rel="next" href="/cars?page=3"></head><a href="/other">Next</a>'
        self.assertEqual(find_next_page_url(html, self.BASE), "https://shop.example.com/cars?page=3")
        self.assertEqual(find_next_page_url('<a rel="next" href="?page=3">go</a>', self.BASE), "https://shop.example.com/cars?page=3")

    def test_a_link_people_read_as_next_is_followed(self):
        for link in ('<a href="/cars?page=3">Next</a>', '<a href="/cars?page=3"> Next page </a>', '<a href="/cars?page=3">›</a>',
                     '<a href="/cars?page=3">»</a>', '<a href="/cars?page=3" aria-label="Next page"><svg></svg></a>', '<a href="/cars?page=3" title="Next">→</a>'):
            self.assertEqual(find_next_page_url(link, self.BASE), "https://shop.example.com/cars?page=3", link)

    def test_other_links_are_not_a_next_page(self):
        for html in ("", "<p>no links</p>", '<a href="/cars?page=1">Previous</a>', '<a href="/about">About us</a>', '<a href="/x">Next steps for buyers</a>',
                     '<a href="javascript:next()">Next</a>', '<a href="#">Next</a>', '<a href="mailto:a@b.c">Next</a>',
                     '<a href="https://ads.other.com/next">Next</a>', '<a href="/cars?page=2">Next</a>', '<a href="https://shop.example.com/cars?page=2#top">Next</a>'):
            self.assertIsNone(find_next_page_url(html, self.BASE), html)

    def test_the_www_prefix_is_the_same_site(self):
        self.assertEqual(find_next_page_url('<a href="https://www.shop.example.com/p3">Next</a>', self.BASE), "https://www.shop.example.com/p3")


class FollowPagesTests(unittest.TestCase):
    def setUp(self):
        self.svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        self.svc.emit_event = lambda *a, **k: None
        self.plan = ScrapePlan(source_name="Shop", entry_url="https://s.test/list", source_url="https://s.test/list", id_field="name")
        self.job = scraper.ScrapeJob(job_id="j", intent=_intent("things"))
        self.pages = {}
        self.fetched = []

    def go(self, max_pages, first_rows=None, extract=None):
        first_html = '<html><a href="/list?p=2">Next</a>' + "x" * 500
        rows = first_rows if first_rows is not None else [{"name": "a"}, {"name": "b"}]

        def fetch(url):
            self.fetched.append(url)
            html = self.pages.get(url)
            if isinstance(html, Exception):
                raise html
            return {"html": html or "", "http_status": 200, "https_ok": len(html or "") > 400}  # fetch_html's shape

        with mock.patch.object(scraper, "fetch_html", fetch), mock.patch.object(scraper.url_access, "record_failure"), \
                mock.patch.object(scraper, "_extract_listing_rows", extract or (lambda html, *a, **k: [{"name": n} for n in html.split("|")[1].split(",")])):
            return self.svc._follow_pages(self.plan, self.job, {"columns": ["name"]}, rows, first_html, "https://s.test/list", max_pages)

    def page(self, names, nxt=None):
        return f"<html>|{','.join(names)}|" + (f'<a href="{nxt}">Next</a>' if nxt else "") + "x" * 500

    def test_pages_are_followed_up_to_the_limit_and_only_new_rows_are_added(self):
        self.pages = {
            "https://s.test/list?p=2": self.page(["c", "d"], "/list?p=3"),
            "https://s.test/list?p=3": self.page(["e"], "/list?p=4"),
            "https://s.test/list?p=4": self.page(["f"]),
        }
        self.assertEqual([r["name"] for r in self.go(3)], ["a", "b", "c", "d", "e"])
        self.assertEqual(self.fetched, ["https://s.test/list?p=2", "https://s.test/list?p=3"])
        self.fetched.clear()
        self.assertEqual([r["name"] for r in self.go(1)], ["a", "b"])
        self.assertEqual(self.fetched, [])

    def test_the_walk_stops_when_a_page_has_nothing_new_or_loops_or_cannot_be_fetched(self):
        self.pages = {"https://s.test/list?p=2": self.page(["a", "b"], "/list?p=3"), "https://s.test/list?p=3": self.page(["z"])}
        self.assertEqual([r["name"] for r in self.go(5)], ["a", "b"], "page 2 repeated page 1: the list is over")
        self.assertEqual(self.fetched, ["https://s.test/list?p=2"])
        self.pages = {"https://s.test/list?p=2": self.page(["c"], "/list?p=2")}
        self.assertEqual([r["name"] for r in self.go(5)], ["a", "b", "c"], "a next link to itself ends it")
        self.pages = {"https://s.test/list?p=2": ConnectionError("down")}
        self.assertEqual([r["name"] for r in self.go(5)], ["a", "b"], "what was read is kept")
        self.pages = {"https://s.test/list?p=2": "<html>tiny"}
        self.assertEqual([r["name"] for r in self.go(5)], ["a", "b"])


class MergeFixTests(unittest.TestCase):
    def test_ev_and_car_must_be_whole_words(self):
        for prompt in ("software development jobs in pune", "every restaurant in delhi", "career counsellors", "carbon credits", "level 3 evaluation centres", "the cargo ships list"):
            self.assertEqual(table_merge.default_columns(_intent(prompt)), ["name", "value", "source"], prompt)
            self.assertFalse(table_merge.intent_avoid_oem_sites(_intent(prompt)), prompt)
        for prompt in ("list all EV cars in india", "electric vehicles with price", "used cars under 5 lakh"):
            self.assertEqual(table_merge.default_columns(_intent(prompt))[0], "car_name", prompt)

    def test_the_ai_cleanup_is_for_short_vehicle_tables_and_cannot_eat_the_table(self):
        columns = ["car_name", "price"]
        rows = [{"car_name": f"Car {i}", "price": "1"} for i in range(10)]
        intent = _intent("list all EV cars with prices")
        with mock.patch.object(table_merge, "gemini_json", return_value={"rows": [{"car_name": "Only one", "price": "1"}]}):
            self.assertEqual(table_merge._ai_refine_table(intent, columns, rows), rows, "a clean-up that removes 90% is rejected")
        keep = [{"car_name": f"Car {i}", "price": "2"} for i in range(9)]
        with mock.patch.object(table_merge, "gemini_json", return_value={"rows": keep}):
            self.assertEqual(table_merge._ai_refine_table(intent, columns, rows), keep, "dropping one junk row is fine")

    def test_merge_does_not_call_the_ai_cleanup_for_other_topics_or_long_tables(self):
        records = [{"source_url": "https://x.test", "data": {"name": f"Item {i}", "value": "1"}} for i in range(10)]
        with mock.patch.object(table_merge, "_ai_refine_table", side_effect=AssertionError("not for this topic")):
            table = table_merge.merge_records(_intent("list all universities in india", "universities"), records)
            self.assertEqual(table["row_count"], 10)
        cars = [{"source_url": "https://x.test", "data": {"car_name": f"Car {i}", "price": "1"}} for i in range(table_merge.AI_REFINE_MAX + 1)]
        with mock.patch.object(table_merge, "_ai_refine_table", side_effect=AssertionError("not for 81 rows")):
            table_merge.merge_records(_intent("list all EV cars"), cars)

    def test_no_model_names_are_added_from_memory(self):
        intent = _intent("list all EV cars in india")
        rows = [{"car_name": "Tata Nexon EV", "price": "1"}]
        with mock.patch("discovery.fetch_html", return_value={"html": ""}), \
                mock.patch.object(table_merge, "gemini_json", return_value={"models": []}) as model:
            out = table_merge.coverage_backfill(intent, rows, ["car_name", "price"])
        self.assertEqual(out, rows)
        self.assertEqual(model.call_count, 1, "only the reference article is read, never a list from the model's memory")


class ScraperFixTests(unittest.TestCase):
    def test_a_url_template_the_model_got_wrong_costs_one_link_not_the_page(self):
        row = {"id": "G-2024-1"}
        for template in ("https://x.test/{slug}/{id}", "https://x.test/{0}", "https://x.test/{", "https://x.test/}{", "https://x.test/{id.attr}"):
            self.assertEqual(plan_scraper.fill_url_template(template, row, "id"), "", template)
        self.assertEqual(plan_scraper.fill_url_template("https://x.test/{year}/{id}", {"id": "A-1-05012024-7"}, "id"), "https://x.test/2024/A-1-05012024-7")  # eGazette ids carry DDMMYYYY

    def test_the_merged_table_is_built_from_every_record_not_the_first_500(self):
        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        job = scraper.ScrapeJob(job_id="j", intent=_intent("things"), table_schema={"columns": ["name"], "column_labels": ["Name"]})
        seen = {}
        svc.list_raw_records = lambda job_id, limit=500: (seen.update(limit=limit) or [])
        svc.save_merged_table = lambda *a, **k: None
        svc.rebuild_merged_table(job)
        self.assertGreaterEqual(seen["limit"], 5000)

    def test_a_live_chat_checks_as_often_as_the_app_says(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(scraper.live_interval_seconds(), 3600)
        for value, want in (("120", 120), ("5", 15), ("", 3600), ("soon", 3600)):
            with mock.patch.dict(os.environ, {"LIVE_SCRAPE_INTERVAL_SEC": value}):
                self.assertEqual(scraper.live_interval_seconds(), want, value)
        from awdax_api.serializers import to_awdax_live_state

        sess = {"id": "c", "created_at": "t", "updated_at": "t", "keep_live": True}
        with mock.patch.dict(os.environ, {"LIVE_SCRAPE_INTERVAL_SEC": "900"}), mock.patch("awdax_api.serializers.dataset_row_count", return_value=0):
            self.assertEqual(to_awdax_live_state(sess)["interval_seconds"], 900)


class ListingCheckTests(unittest.TestCase):
    PAGE = {"html": "<html><body>" + "<div class='card'>Laptop X - Rs 45,000</div>" * 40 + "</body></html>"}

    def ask(self, answer, page=None):
        with mock.patch.object(inspector, "fetch_html", return_value=page or self.PAGE), mock.patch.object(inspector, "gemini_json", return_value=answer):
            return inspector.llm_listing_estimate(_intent("laptops under 50000"), "https://shop.test/laptops")

    def test_a_card_layout_catalogue_counts_as_a_list(self):
        self.assertEqual(self.ask({"has_listing": True, "estimated_items": 24}), 24)
        self.assertEqual(self.ask({"has_listing": True}), 1)
        self.assertEqual(self.ask({"has_listing": True, "estimated_items": 99999}), 500)

    def test_an_article_a_tiny_page_or_an_unavailable_model_is_not(self):
        self.assertEqual(self.ask({"has_listing": False, "estimated_items": 12}), 0)
        self.assertEqual(self.ask("not an object"), 0)
        self.assertEqual(self.ask({"has_listing": "true"}), 0)
        self.assertEqual(self.ask({"has_listing": True}, page={"html": "<html>short</html>"}), 0)
        with mock.patch.object(inspector, "fetch_html", return_value=self.PAGE), mock.patch.object(inspector, "gemini_json", side_effect=RuntimeError("down")):
            self.assertEqual(inspector.llm_listing_estimate(_intent("x"), "https://shop.test/"), 0)
        with mock.patch.object(inspector, "fetch_html", side_effect=ConnectionError("down")):
            self.assertEqual(inspector.llm_listing_estimate(_intent("x"), "https://shop.test/"), 0)

    def inspect(self, estimate):
        plan = ScrapePlan(source_name="Shop", entry_url="https://shop.test/laptops", source_url="https://shop.test/laptops", confidence=0.9)
        probe = {"https_ok": True, "final_url": "https://shop.test/laptops", "http_status": 200, "title": "Laptops", "table_count": 0, "table_headers_preview": []}
        with mock.patch.object(inspector, "probe_https", return_value=probe), \
                mock.patch.object(inspector, "_probe_page_selenium", return_value={"tables": [], "hard_blocked": False, "title": "Laptops"}), \
                mock.patch.object(inspector, "_plan_from_gemini", return_value=plan), mock.patch.object(inspector, "dry_run_plan", return_value=0), \
                mock.patch.object(inspector, "llm_listing_estimate", return_value=estimate) as check:
            from discovery import SourceCandidate

            return inspector.inspect_source(_intent("laptops under 50000"), SourceCandidate(url="https://shop.test/laptops")), check

    def test_a_source_with_no_table_is_accepted_when_the_model_sees_a_list(self):
        plan, check = self.inspect(24)
        self.assertFalse(plan.blocked)
        self.assertEqual((plan.dry_run_rows, check.call_count), (20, 1))
        self.assertLessEqual(plan.confidence, 0.55)
        self.assertIn("read by the AI", " ".join(plan.warnings))

    def test_and_rejected_as_before_when_there_is_nothing_to_read(self):
        plan, _ = self.inspect(0)
        self.assertTrue(plan.blocked)
        self.assertIn("No table/list data", " ".join(plan.warnings))


class PageReachTests(unittest.TestCase):
    def test_a_long_page_is_read_far_enough_to_reach_its_later_tables(self):
        """Wikipedia's list of IITs puts the 23-row table past 200k characters; the old cap kept only 17 of the rows."""
        import discovery

        body = "<html><body>" + "<p>filler text</p>" * 30_000 + "<table><tr><td>last row</td></tr></table></body></html>"
        self.assertGreater(len(body), 200_000)
        fake = mock.Mock(text=body, url="https://example.org/long", status_code=200, headers={})
        with mock.patch.object(discovery, "safe_get", return_value=fake):
            html = discovery.fetch_html("https://example.org/long")["html"]
        self.assertIn("last row", html)

    def test_a_ready_step_without_a_selector_is_skipped_not_reported(self):
        steps = [{"action": "click"}, {"action": "click", "selector": "  "}, "junk"]
        runner = plan_scraper.PlanDrivenScraper.__new__(plan_scraper.PlanDrivenScraper)
        runner.plan = ScrapePlan(source_name="s", entry_url="https://example.org", listing_ready_steps=steps)
        runner.driver = mock.Mock()
        with mock.patch.object(plan_scraper, "WebDriverWait") as wait, self.assertNoLogs("plan_scraper", level="WARNING"):
            runner.run_ready_steps()
        wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()
