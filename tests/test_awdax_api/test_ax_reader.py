"""Reading a page through the browser's accessibility tree: the tree as text, the pager, and the walk through the pages.
No test opens a browser or reaches the network."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ax_reader  # noqa: E402
import gemini_scrape  # noqa: E402
import inspector  # noqa: E402
import scraper  # noqa: E402
from inspector import ScrapePlan  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402


def node(i, role, name="", children=(), parent=None, ignored=False, backend=None, props=None):
    n = {"nodeId": str(i), "role": {"value": role}, "name": {"value": name}, "childIds": [str(c) for c in children], "ignored": ignored}
    if parent is not None:
        n["parentId"] = str(parent)
    if backend:
        n["backendDOMNodeId"] = backend
    if props:
        n["properties"] = props
    return n


def listing_tree(extra=()):
    """navigation | main: table with a header and two rows, a list of two cards | contentinfo."""
    nodes = [
        node(1, "RootWebArea", children=[2, 3, 20, 30, *[e["nodeId"] for e in extra]]),
        node(2, "navigation", "Site", children=[21], parent=1),
        node(21, "link", "Home", parent=2),
        node(3, "table", "", children=[4, 5, 6], parent=1),
        node(4, "row", children=[7, 8], parent=3),
        node(7, "columnheader", "Title", parent=4),
        node(8, "columnheader", "Year", parent=4),
        node(5, "row", children=[9, 10], parent=3),
        node(9, "cell", "Need for AIIMS", parent=5),
        node(10, "cell", "2025", parent=5),
        node(6, "row", children=[11, 12], parent=3),
        node(11, "cell", "Waterways", parent=6),
        node(12, "cell", "2024", parent=6),
        node(20, "article", "", children=[22], parent=1),
        node(22, "link", "A Light in the Attic", children=[23], parent=20),
        node(23, "StaticText", "A Light in the Attic", parent=22),
        node(30, "contentinfo", "", children=[31], parent=1),
        node(31, "link", "Privacy policy", parent=30),
    ]
    return nodes + list(extra)


class TreeTextTests(unittest.TestCase):
    def test_rows_cards_and_controls_become_single_lines_and_furniture_is_left_out(self):
        text = ax_reader.tree_text(listing_tree(), max_chars=10_000)
        lines = text.splitlines()
        self.assertIn("row: Title | Year", lines[1])
        self.assertIn("row: Need for AIIMS | 2025", text)
        self.assertIn("row: Waterways | 2024", text)
        self.assertIn("article: A Light in the Attic", text)
        self.assertEqual(text.count("A Light in the Attic"), 1, "text that repeats its parent's name is dropped")
        self.assertNotIn("Home", text)
        self.assertNotIn("Privacy policy", text)

    def test_landmarks_come_back_when_leaving_them_out_would_leave_nothing(self):
        only_menu = [node(1, "RootWebArea", children=[2], parent=None), node(2, "navigation", "Site", children=[3], parent=1), node(3, "link", "Home", parent=2)]
        self.assertIn("link \"Home\"", ax_reader.tree_text(only_menu))

    def test_it_is_cut_at_the_limit_and_item_counts_come_from_the_lines(self):
        text = ax_reader.tree_text(listing_tree(), max_chars=40)
        self.assertLessEqual(len(text), 40)
        full = ax_reader.tree_text(listing_tree(), max_chars=10_000)
        self.assertEqual(ax_reader.item_estimate(full), 2, "two data rows (the header row is not counted) and one card")
        self.assertEqual(ax_reader.item_estimate("heading \"An article\"\ntext \"words\""), 0)
        self.assertEqual(ax_reader.item_estimate("\n".join(f"- item {i}" for i in range(6))), 6)
        self.assertEqual(ax_reader.tree_text([]), "")


class PagerTests(unittest.TestCase):
    def pager(self, *controls):
        children = list(range(40, 40 + len(controls)))
        nodes = [node(1, "RootWebArea", children=children)] + [
            node(40 + i, role, name, parent=1, backend=100 + i, props=props) for i, (role, name, props) in enumerate(controls)
        ]
        return nodes

    def test_the_next_control_is_found_whatever_it_is_called(self):
        for name in ("Go to next page", "Next", "next page", "Next ›", "›", "»", "Older posts", "Load more", "Show more results"):
            found = ax_reader.pager_target(self.pager(("button", "Go to page 2", None), ("link", name, None)))
            self.assertIsNotNone(found, name)
            self.assertEqual(found["backendDOMNodeId"], 101, name)
        for name in ("Go to page 2", "Contact us", "Previous", "Nextel phones"):
            self.assertIsNone(ax_reader.pager_target(self.pager(("button", name, None))), name)

    def test_a_disabled_control_and_the_last_of_several_are_handled(self):
        disabled = [{"name": "disabled", "value": {"value": True}}]
        self.assertIsNone(ax_reader.pager_target(self.pager(("button", "Next", disabled))))
        both = ax_reader.pager_target(self.pager(("link", "Next", None), ("button", "Go to next page", None)))
        self.assertEqual(both["backendDOMNodeId"], 101, "a pager sits after the list, so the last one is taken")

    def test_pressing_it_waits_for_the_content_to_change(self):
        driver = mock.Mock()
        before, after = listing_tree(), listing_tree([node(50, "heading", "Page two", parent=1)])
        target = {"backendDOMNodeId": 7}
        seen = iter([before, before, after])
        with mock.patch.object(ax_reader, "nodes", side_effect=lambda d: next(seen)), mock.patch.object(ax_reader.time, "sleep"), \
                mock.patch("inspector.wait_until_settled"), mock.patch.object(ax_reader, "click") as click:
            self.assertTrue(ax_reader.advance(driver, before, target, wait_s=30))
        click.assert_called_once_with(driver, target)
        with mock.patch.object(ax_reader, "nodes", return_value=before), mock.patch.object(ax_reader, "click"), \
                mock.patch.object(ax_reader.time, "sleep"), mock.patch.object(ax_reader.time, "time", side_effect=[0, 1, 99, 99]):
            self.assertFalse(ax_reader.advance(driver, before, target, wait_s=10), "a pager that changes nothing is the end of the list")
        with mock.patch.object(ax_reader, "click", side_effect=RuntimeError("detached")):
            self.assertFalse(ax_reader.advance(driver, before, target))

    def test_rows_seen_on_an_earlier_page_are_not_new(self):
        seen = set()
        self.assertEqual(len(ax_reader.fresh_rows([{"a": "X "}, {"a": "y"}, {"a": ""}], seen)), 2)
        self.assertEqual(ax_reader.fresh_rows([{"a": "x"}, {"a": "z"}], seen), [{"a": "z"}])


class TreeExtractionTests(unittest.TestCase):
    INTENT = ScrapeIntent(job_id="j", topic="debates", raw_prompt="list the debates")

    def test_the_model_gets_the_tree_and_returns_rows(self):
        tree = "\n".join(f"row: Debate {i} | 2025" for i in range(40))
        with mock.patch.object(gemini_scrape, "gemini_json", return_value={"rows": [{"title": "Debate 1", "year": "2025"}, {"title": "", "year": ""}]}) as ask:
            rows = gemini_scrape.gemini_extract_rows_from_tree(tree, self.INTENT, ["title", "year"], page_url="https://s.test")
        self.assertEqual(rows, [{"title": "Debate 1", "year": "2025"}])
        prompt = ask.call_args.args[0]
        self.assertIn("accessibility_tree", prompt)
        self.assertIn("one line `row: cell | cell`", prompt)
        self.assertEqual(gemini_scrape.gemini_extract_rows_from_tree("short", self.INTENT, ["title"]), [])

    def test_a_long_tree_is_read_in_parts_and_a_failed_part_loses_only_itself(self):
        tree = "\n".join(f"row: Debate number {i:04d} | 2025" for i in range(300))
        answers = iter([{"rows": [{"title": "a"}]}, RuntimeError("busy"), {"rows": [{"title": "c"}]}])

        def ask(prompt, temperature=0):
            a = next(answers)
            if isinstance(a, Exception):
                raise a
            return a

        with mock.patch.dict(os.environ, {"AX_CHUNK_CHARS": "4000"}), mock.patch.object(gemini_scrape, "gemini_json", side_effect=ask) as call:
            rows = gemini_scrape.gemini_extract_rows_from_tree(tree, self.INTENT, ["title"])
        self.assertEqual([r["title"] for r in rows], ["a", "c"])
        self.assertEqual(call.call_count, 3)
        self.assertIn("part 1 of 3", call.call_args_list[0].args[0])

    def test_a_truncated_link_text_gets_its_full_title_back(self):
        html = '<h3><a href="x" title="A Light in the Attic">A Light in the ...</a></h3><a href="y" title="Other">Short</a><a title="Soumission">Soumi…</a>'
        fixed = gemini_scrape.restore_truncated_text(html)
        self.assertIn(">A Light in the Attic</a>", fixed)
        self.assertIn(">Short</a>", fixed, "a link that is not cut off is left alone")
        self.assertIn(">Soumission</a>", fixed)


class FakeDriver:
    def __init__(self):
        self.quit_called = False
        self.url = None

    def quit(self):
        self.quit_called = True


class BrowserRowsTests(unittest.TestCase):
    def setUp(self):
        self.svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        self.svc.emit_event = mock.Mock()
        self.svc._cancelled_jobs = set()
        self.plan = ScrapePlan(source_name="LS", entry_url="https://s.test/d", source_url="https://s.test/d", id_field="title")
        self.job = scraper.ScrapeJob(job_id="jb", intent=ScrapeIntent(job_id="jb", topic="debates", raw_prompt="list the debates"),
                                     table_schema={"columns": ["title", "year"], "column_labels": ["Title", "Year"]})
        self.driver = FakeDriver()

    def run_pages(self, per_page, pages, *, pager=True, advance=True):
        answers = iter(per_page)
        tree = "row: x | 1\n" * 40
        with mock.patch("inspector._setup_driver", return_value=self.driver), mock.patch("inspector.load_page"), mock.patch("inspector.wait_until_settled"), \
                mock.patch.object(ax_reader, "nodes", return_value=[{"nodeId": "1"}]), mock.patch.object(ax_reader, "tree_text", return_value=tree), \
                mock.patch.object(ax_reader, "pager_target", return_value={"backendDOMNodeId": 1} if pager else None), \
                mock.patch.object(ax_reader, "advance", return_value=advance) as adv, \
                mock.patch.object(gemini_scrape, "gemini_extract_rows_from_tree", side_effect=lambda *a, **k: next(answers)) as read:
            rows = self.svc._browser_rows(self.plan, self.job, self.job.table_schema, "https://s.test/d", pages)
        return rows, adv, read

    def test_the_pager_is_pressed_page_after_page_up_to_the_limit(self):
        pages = [[{"title": f"p{p}-{i}", "year": "2025"} for i in range(10)] for p in range(5)]
        rows, adv, read = self.run_pages(pages, 3)
        self.assertEqual(len(rows), 30)
        self.assertEqual((read.call_count, adv.call_count), (3, 2), "three pages read, the pager pressed between them")
        self.assertTrue(self.driver.quit_called)

    def test_it_stops_at_a_page_with_nothing_new_a_missing_pager_or_a_pager_that_changes_nothing(self):
        same = [{"title": "debate a", "year": "1"}]
        rows, _, read = self.run_pages([same, same, same], 5)
        self.assertEqual((len(rows), read.call_count), (1, 2), "the repeated page ends the walk")
        rows, adv, _ = self.run_pages([[{"title": "debate a", "year": "1"}]], 5, pager=False)
        self.assertEqual((len(rows), adv.call_count), (1, 0))
        rows, adv, read = self.run_pages([[{"title": "debate a", "year": "1"}], [{"title": "debate b", "year": "1"}]], 5, advance=False)
        self.assertEqual((len(rows), read.call_count), (1, 1))

    def test_a_page_that_cannot_be_read_is_recorded_and_left_to_the_html_path(self):
        with mock.patch("inspector._setup_driver", return_value=self.driver), mock.patch("inspector.load_page", side_effect=RuntimeError("timeout")), \
                mock.patch.object(scraper.url_access, "record_failure") as record:
            self.assertEqual(self.svc._browser_rows(self.plan, self.job, self.job.table_schema, "https://s.test/d", 3), [])
        self.assertEqual(record.call_args.kwargs["outcome"], "error")
        self.assertTrue(self.driver.quit_called)

    def test_the_listing_reads_a_javascript_page_through_the_tree_and_falls_back_to_its_html(self):
        plain = {"html": "<html>" + "<p>text</p>" * 5 + "</html>", "http_status": 200, "https_ok": True}
        self.plan.render = True
        with mock.patch.object(scraper, "fetch_html", return_value=plain), mock.patch.object(self.svc, "_browser_rows", return_value=[{"title": "debate a"}]) as tree, \
                mock.patch.object(scraper, "_fetch_html_for_gemini") as html_path:
            self.assertEqual(self.svc._listing_rows(self.plan, self.job, 3), [{"title": "debate a"}])
        tree.assert_called_once()
        html_path.assert_not_called()
        with mock.patch.object(scraper, "fetch_html", return_value=plain), mock.patch.object(self.svc, "_browser_rows", return_value=[]), \
                mock.patch.object(scraper, "_fetch_html_for_gemini", return_value="") as html_path:
            self.assertEqual(self.svc._listing_rows(self.plan, self.job, 3), [])
        html_path.assert_called_once()
        with mock.patch.dict(os.environ, {"AX_READER": "0"}), mock.patch.object(scraper, "fetch_html", return_value=plain), \
                mock.patch.object(self.svc, "_browser_rows") as tree, mock.patch.object(scraper, "_fetch_html_for_gemini", return_value=""):
            self.svc._listing_rows(self.plan, self.job, 3)
        tree.assert_not_called()

    def test_a_static_page_is_not_opened_in_a_browser(self):
        static = {"html": "<html><body>" + "<p>plenty of ordinary readable words here</p>" * 400 + "</body></html>", "http_status": 200, "https_ok": True}
        with mock.patch.object(scraper, "fetch_html", return_value=static), mock.patch.object(self.svc, "_browser_rows") as tree, \
                mock.patch.object(scraper, "_fetch_html_for_gemini", return_value=""):
            self.svc._listing_rows(self.plan, self.job, 3)
        tree.assert_not_called()


class InspectionUsesTheTreeTests(unittest.TestCase):
    def test_the_plan_prompt_gets_the_pages_outline_and_cards_are_counted_without_a_table(self):
        outline = "heading \"Books\"\n" + "\n".join(f"article: Book {i} ; £{i}.99" for i in range(20))
        view = inspector._signals_for_prompt({"tables": [], "ax_text": outline + "x" * 9000, "rendered_html": "<p>" + "w " * 4000 + "</p>"})
        self.assertNotIn("ax_text", view)
        self.assertLessEqual(len(view["page_outline"]), 3500)
        self.assertNotIn("visible_text_sample", view)
        self.assertEqual(inspector.rendered_row_count({"ax_text": outline}), 20)

    def test_a_page_whose_content_comes_from_javascript_is_flagged_for_the_tree(self):
        shell = "<html><body>" + "<p>Rows appear here once the script has run, a lot of text.</p>" * 120 + "</body></html>"
        probe = {"https_ok": True, "http_status": 200, "final_url": "https://s.test/d", "table_count": 0, "table_headers_preview": [], "visible_chars": 200}
        signals = {"tables": [], "hard_blocked": False, "rendered_html": shell, "feed": None}
        with mock.patch.object(inspector, "probe_https", return_value=probe), mock.patch.object(inspector.url_access, "record_probe"), \
                mock.patch.object(inspector, "_probe_page_selenium", return_value=signals), mock.patch.object(inspector, "llm_listing_estimate", return_value=0), \
                mock.patch.object(inspector, "gemini_json", return_value={"source_name": "S", "holds_requested_records": True}):
            plan = inspector.inspect_source(ScrapeIntent(job_id="j", topic="t", raw_prompt="t"), inspector.SourceCandidate(url="https://s.test/d", domain="s.test"))
            self.assertTrue(plan.render)
            probe["visible_chars"] = 8000  # the plain page already had the text: nothing for JavaScript to add
            plan = inspector.inspect_source(ScrapeIntent(job_id="j", topic="t", raw_prompt="t"), inspector.SourceCandidate(url="https://s.test/d", domain="s.test"))
            self.assertFalse(plan.render)
        self.assertTrue(ScrapePlan.from_dict({**plan.to_dict(), "render": True}).render, "kept when the plan is saved")


if __name__ == "__main__":
    unittest.main()
