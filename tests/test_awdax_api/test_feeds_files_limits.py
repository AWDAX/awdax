"""The data feed behind a JavaScript table, downloadable data files, and the period a request limits its rows to.
No test reaches the network."""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import data_feed  # noqa: E402
import dataset_files  # noqa: E402
import row_limits  # noqa: E402
import scraper  # noqa: E402
from inspector import ScrapePlan  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402
from row_limits import Period, apply_period, parse_date, period_from_text  # noqa: E402


def _intent(prompt):
    return ScrapeIntent(job_id="job-f", topic=prompt, raw_prompt=prompt)


class PeriodTests(unittest.TestCase):
    def test_periods_are_read_from_the_request(self):
        today = date(2026, 10, 7)
        cases = {
            "give me parliamentary debates in india between 2010 to 2025": (date(2010, 1, 1), date(2025, 12, 31)),
            "fifa world cup finals from 1990 to 2010": (date(1990, 1, 1), date(2010, 12, 31)),
            "budgets 2015-2020": (date(2015, 1, 1), date(2020, 12, 31)),
            "startups founded since 2015": (date(2015, 1, 1), None),
            "cars launched after 2020": (date(2021, 1, 1), None),
            "laws passed before 2000": (None, date(1999, 12, 31)),
            "budgets in 2023": (date(2023, 1, 1), date(2023, 12, 31)),
            "earthquakes in the last 3 years": (date(2023, 10, 7), today),
        }
        for text, (start, end) in cases.items():
            self.assertEqual(period_from_text(text, today=today), Period(start, end), text)
        for text in ("list all the IITs in India with their city and year established", "top universities 2024 ranking", ""):
            self.assertIsNone(period_from_text(text, today=today), text)

    def test_dates_as_pages_write_them(self):
        cases = {
            "2025-02-04": date(2025, 2, 4), "30-Jul-2026": date(2026, 7, 30), "15/03/2021": date(2021, 3, 15),
            "12/31/2020": date(2020, 12, 31), "July 22, 2024": date(2024, 7, 22), "4 February 2025": date(2025, 2, 4),
            "Feb 2019": date(2019, 2, 1), "1992": date(1992, 1, 1), "2015 [ 60 ]": date(2015, 1, 1), "2015-16": date(2015, 1, 1),
            "2025-04-04T10:00:00Z": date(2025, 4, 4),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_date(text), expected, text)
        for text in ("", "abc", "IIT Bombay", "31/31/2020"):
            self.assertIsNone(parse_date(text), text)

    def test_rows_outside_the_period_are_dropped_and_undated_rows_kept(self):
        cols = ["debate_title", "date", "source_url"]
        rows = [
            {"debate_title": "a", "date": "2025-02-04"},
            {"debate_title": "b", "date": "30-Jul-2026"},
            {"debate_title": "c", "date": "15/03/2009"},
            {"debate_title": "d", "date": ""},
            {"debate_title": "e", "date": "13-Aug-2010"},
        ]
        kept, dropped = apply_period(rows, cols, Period(date(2010, 1, 1), date(2025, 12, 31)))
        self.assertEqual([r["debate_title"] for r in kept], ["a", "d", "e"])
        self.assertEqual(dropped, 2)
        self.assertEqual(apply_period(rows, cols, None), (rows, 0))

    def test_the_dating_column_is_found_even_when_not_named_date(self):
        rows = [{"final": "Germany v Argentina", "held_in": "2014"}, {"final": "Spain v Netherlands", "held_in": "2010"}]
        self.assertEqual(row_limits.date_column(rows, ["final", "held_in"]), "held_in")

    def test_the_store_never_keeps_a_row_outside_the_period(self):
        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        svc._status_by_job = {}
        svc.emit_event = mock.Mock()
        svc._set_status = mock.Mock()
        svc._running_jobs = set()
        job = scraper.ScrapeJob(job_id="j1", intent=_intent("debates between 2010 to 2025"), table_schema={"columns": ["title", "date"]})
        plan = ScrapePlan(source_name="RS", entry_url="https://s.test")
        with mock.patch.object(svc, "store_record", return_value=None) as store, mock.patch.object(svc, "is_job_live", return_value=False):
            svc._store_rows(plan, job, [{"title": "in", "date": "2024-01-01"}, {"title": "out", "date": "2026-07-30"}])
        self.assertEqual([c.args[2]["title"] for c in store.call_args_list], ["in"])
        logged = " ".join(str(c.args[1].get("message")) for c in svc.emit_event.call_args_list)
        self.assertIn("1 rows dated outside 2010-01-01 to 2025-12-31 left out", logged)


LS_PAGE_TEXT = "Debate Search The Speaker on behalf of the House Congratulated Indian Sportspersons 30/07/2026 FELICITATIONS Shri Om Birla Ruling regarding Notices of Adjournment Motion RULING BY THE SPEAKER Smt. Sandhya Ray"
LS_FEED = "https://sansad.example/api/debate-search?loksabha=18&fromDate=&toDate=&page=1&size=10&locale=en%20%20"
LS_BODY = {
    "_metadata": {"currentPageNumber": 1, "perPageSize": 10, "totalElements": 25, "totalPages": 3},
    "records": [
        {"debateTitle": "The Speaker on behalf of the House Congratulated Indian Sportspersons", "debateDate": "30/07/2026",
         "debateTypeDesc": "FELICITATIONS", "memberName": "['Shri Om Birla']"},
        {"debateTitle": "Ruling regarding Notices of Adjournment Motion", "debateDate": "30/07/2026",
         "debateTypeDesc": "RULING BY THE SPEAKER", "memberName": "['Smt. Sandhya Ray']"},
        {"debateTitle": "Papers Laid on the table", "debateDate": "30/07/2026", "debateTypeDesc": "PAPERS LAID ON THE TABLE",
         "memberName": "['Shri Tokhan Sahu', 'Shri Murlidhar Mohol']"},
    ],
}
FACETS = ("https://sansad.example/api/browse?field=type", {"records": [{"name": "FELICITATIONS", "count": 9}, {"name": "RULING BY THE SPEAKER", "count": 4}, {"name": "OTHER", "count": 1}]})


class FeedTests(unittest.TestCase):
    def test_the_feed_is_the_response_whose_records_are_the_rows_on_screen(self):
        feed = data_feed.recognise([FACETS, (LS_FEED, LS_BODY), ("https://x.test/menu", {"items": [{"a": 1, "b": 2}] * 5})], LS_PAGE_TEXT)
        self.assertEqual(feed.url, LS_FEED)
        self.assertEqual((feed.path, feed.total, feed.page_key, feed.size_key, feed.size), (["records"], 25, "page", "size", 10))
        self.assertIsNone(data_feed.recognise([FACETS], "nothing like it on screen"))

    def test_pages_are_walked_with_a_larger_size_and_the_requested_period(self):
        feed = data_feed.recognise([(LS_FEED, LS_BODY)], LS_PAGE_TEXT)
        asked = []

        def fetch(url, referer):
            asked.append(url)
            page = int(dict(p.split("=", 1) for p in url.split("?")[1].split("&"))["page"])
            n = {1: 100, 2: 100, 3: 37}.get(page, 0)
            return {"_metadata": {"totalElements": 237}, "records": [{"debateTitle": f"p{page}-{i}", "debateDate": "01/02/2020"} for i in range(n)]}

        with mock.patch.object(data_feed, "_fetch_json", side_effect=fetch):
            rows = data_feed.collect(feed, referer="https://s.test", max_rows=1000, period=(date(2010, 1, 1), date(2025, 12, 31)))
        self.assertEqual(len(rows), 237)
        self.assertEqual(len(asked), 3, "stops at the reported total")
        self.assertIn("fromDate=01%2F01%2F2010", asked[0].replace("/", "%2F")) if "%2F" in asked[0] else self.assertIn("fromDate=01/01/2010", asked[0])
        self.assertIn("toDate=31/12/2025", asked[0])
        self.assertIn("size=100", asked[0])
        self.assertIn("locale=en%20%20", asked[0], "the page's own parameters are sent back as they were")

    def test_offset_paging_a_refused_size_and_a_feed_that_repeats_itself(self):
        body = {"rowsCount": "746595", "records": [{"title": f"Debate number {i}", "date": "2025-02-04"} for i in range(50)]}
        feed = data_feed.recognise([("https://rs.test/fetch/all?start=0&rows=50&collectionId=(1,2)", body)], " ".join(f"Debate number {i}" for i in range(50)))
        self.assertEqual((feed.offset_key, feed.size_key, feed.total), ("start", "rows", 746595))
        calls = []

        def fetch(url, referer):
            calls.append(url)
            if "rows=100" in url:
                raise RuntimeError("HTTP 400")
            return body  # ignores paging: same first record every time

        with mock.patch.object(data_feed, "_fetch_json", side_effect=fetch):
            rows = data_feed.collect(feed, referer="https://rs.test", max_rows=500)
        self.assertEqual(len(rows), 50, "a repeated page ends the walk")
        self.assertIn("rows=50", calls[-1])
        self.assertIn("collectionId=(1,2)", calls[-1])

    def test_values_are_flattened_and_mapped(self):
        self.assertEqual(data_feed._flat("['Shri Tokhan Sahu', 'Shri Murlidhar Mohol']"), "Shri Tokhan Sahu, Shri Murlidhar Mohol")
        self.assertEqual(data_feed._flat([{"mpName": "A", "mpCode": 1}, {"mpName": "B"}]), "A, B")
        self.assertEqual(data_feed._flat(None), "")
        rows = data_feed.to_rows(LS_BODY["records"], {"title": ["debateTitle"], "member": ["memberName"], "empty": []})
        self.assertEqual(rows[2], {"title": "Papers Laid on the table", "member": "Shri Tokhan Sahu, Shri Murlidhar Mohol", "empty": ""})

    def test_column_mapping_uses_the_model_and_falls_back_to_same_names(self):
        with mock.patch("reasoning.gemini_json", return_value={"mapping": {"date": ["debateDate"], "title": ["debateTitle", "nope"]}}):
            self.assertEqual(data_feed.column_mapping(LS_BODY["records"], ["date", "title"], ["Date", "Title"], "g"), {"date": ["debateDate"], "title": ["debateTitle"]})
        with mock.patch("reasoning.gemini_json", side_effect=RuntimeError("down")):  # a busy model costs accuracy, not the rows
            self.assertEqual(data_feed.column_mapping([{"debate_date": "x", "b": 1}], ["debateDate"], ["Date"], "g"), {"debateDate": ["debate_date"]})
        with mock.patch("reasoning.gemini_json", return_value={}):
            self.assertEqual(data_feed.column_mapping([{"debate_date": "x", "b": 1}], ["debateDate"], ["Date"], "g"), {"debateDate": ["debate_date"]})

    def test_a_javascript_table_is_read_from_its_feed_before_the_page(self):
        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        svc.emit_event = mock.Mock()
        job = scraper.ScrapeJob(job_id="j", intent=_intent("debates between 2010 to 2025"), table_schema={"columns": ["title", "date"], "column_labels": ["Title", "Date"]})
        plan = ScrapePlan(source_name="LS", entry_url="https://s.test/debates", source_url="https://s.test/debates")
        shell = {"html": "<html>" + "<script>x</script>" * 2000 + "<div id=root></div></html>", "http_status": 200, "https_ok": True}
        with mock.patch.object(scraper, "fetch_html", return_value=shell), \
                mock.patch("data_feed.read_feed", return_value=[{"title": "t1", "date": "2020-01-01"}, {"title": "t2", "date": "2020-01-01"}]) as feed, \
                mock.patch.object(scraper, "_fetch_html_for_gemini") as page:
            rows = svc._listing_rows(plan, job)
        self.assertEqual([r["title"] for r in rows], ["t1", "t2"])
        self.assertEqual(feed.call_args.kwargs["period"], (date(2010, 1, 1), date(2025, 12, 31)))
        page.assert_not_called()


def _xlsx(rows):
    """A minimal .xlsx: shared strings for text, numbers inline."""
    strings, xml_rows = [], []
    for i, row in enumerate(rows, start=1):
        cells = []
        for j, v in enumerate(row):
            ref = f"{chr(65 + j)}{i}"
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                strings.append(v)
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        xml_rows.append(f'<row r="{i}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel_ns}><sheets><sheet name="Data" sheetId="1" r:id="rId7"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId7" Target="worksheets/data.xml"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/data.xml", f'<worksheet {ns}><sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    return buf.getvalue()


class ValueFilterTests(unittest.TestCase):
    RECS = [{"Country Name": c, "Year": y, "Value": "1"} for c in ("India", "Japan") for y in ("2010", "2011")]

    def test_rows_of_the_named_value_are_kept_and_a_misnamed_value_never_empties_the_table(self):
        with mock.patch("reasoning.gemini_json", return_value={"filters": [{"field": "Country Name", "values": ["India"]}]}):
            filters = data_feed.value_filters(self.RECS, "GDP of India")
        self.assertEqual(filters, {"Country Name": ["India"]})
        self.assertEqual({r["Country Name"] for r in data_feed.apply_value_filters(self.RECS, filters)}, {"India"})
        with mock.patch("reasoning.gemini_json", return_value={"filters": [{"field": "Country Name", "values": ["Bharat"]}, {"field": "nope", "values": ["x"]}]}):
            self.assertEqual(data_feed.value_filters(self.RECS, "GDP of Bharat"), {})
        with mock.patch("reasoning.gemini_json", side_effect=RuntimeError("down")):
            self.assertEqual(data_feed.value_filters(self.RECS, "x"), {})


class DatasetFileTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._dir.cleanup)
        tmp = mock.patch.object(dataset_files, "TEMP_DIR", self._dir.name)
        tmp.start()
        self.addCleanup(tmp.stop)

    def test_file_links_are_found_and_github_pages_point_at_the_file(self):
        html = """<a href="/files/debates.csv?download=1">CSV</a> <a href="data.xlsx">Excel</a> <a href="/about">About</a>
        <a href="https://github.com/o/r/blob/main/data/x.json">x</a> <a href="#top">top</a> <a href="/files/debates.csv?download=1">again</a>"""
        self.assertEqual(dataset_files.find_dataset_links(html, "https://repo.test/records/1"), [
            "https://repo.test/files/debates.csv?download=1", "https://repo.test/records/data.xlsx", "https://raw.githubusercontent.com/o/r/main/data/x.json",
        ])

    def test_csv_tsv_json_and_xlsx_are_read(self):
        csv_bytes = "﻿note\nTitle,Date,House\nNeed for AIIMS,2025-02-04,Rajya Sabha\n\"Budget, 2024\",2024-07-23,Lok Sabha\n".encode("utf-8")
        self.assertEqual(dataset_files.read_csv(csv_bytes)[1], {"Title": "Budget, 2024", "Date": "2024-07-23", "House": "Lok Sabha"})
        self.assertEqual(dataset_files.read_csv(b"a\tb\n1\t2\n", delimiter="\t"), [{"a": "1", "b": "2"}])
        self.assertEqual(len(dataset_files.read_json(json.dumps({"data": {"rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}}).encode())), 2)
        recs = dataset_files.read_xlsx(_xlsx([["Title", "Year"], ["Debate A", 2015], ["Debate B", 2019]]))
        self.assertEqual(recs, [{"Title": "Debate A", "Year": "2015"}, {"Title": "Debate B", "Year": "2019"}])

    def test_a_download_is_capped_and_a_web_page_is_not_a_file(self):
        ok = mock.Mock(status_code=200, content=b"a,b\n1,2\n")
        with mock.patch("url_guard.safe_get", return_value=ok):
            path = dataset_files.download("https://d.test/x.csv")
        self.assertTrue(os.path.exists(path) and path.startswith(self._dir.name))
        with mock.patch("url_guard.safe_get", return_value=mock.Mock(status_code=200, content=b"<!DOCTYPE html><html>login</html>")), self.assertRaises(RuntimeError):
            dataset_files.download("https://d.test/x.csv")
        with mock.patch("url_guard.safe_get", return_value=mock.Mock(status_code=200, content=b"x" * 3000)), self.assertRaises(RuntimeError):
            dataset_files.download("https://d.test/x.csv", max_mb=0.001)
        with mock.patch("url_guard.safe_get", return_value=mock.Mock(status_code=403, content=b"")), self.assertRaises(RuntimeError):
            dataset_files.download("https://d.test/x.csv")

    def test_a_refused_plain_download_is_recorded_and_fetched_with_the_browser(self):
        refused = []
        path = os.path.join(self._dir.name, "ds-x.csv")
        with open(path, "wb") as f:
            f.write(b"a,b\n1,2\n")
        with mock.patch("url_guard.safe_get", return_value=mock.Mock(status_code=403, content=b"")),                 mock.patch.object(dataset_files, "browser_download", return_value=path) as browser:
            recs = dataset_files.records_from("https://z.test/f.csv?download=1", owner="o1", on_refused=refused.append)
        self.assertEqual(recs, [{"a": "1", "b": "2"}])
        self.assertEqual(refused, ["HTTP 403"])
        browser.assert_called_once()
        self.assertEqual(dataset_files.release("o1"), 1)
        self.assertFalse(os.path.exists(path))
        with mock.patch("url_guard.safe_get", return_value=mock.Mock(status_code=200, content=b"<html>x</html>")),                 mock.patch.object(dataset_files, "browser_download") as browser, self.assertRaises(RuntimeError):
            dataset_files.records_from("https://z.test/f.csv", owner="o2")
        browser.assert_not_called()

    def test_files_are_kept_until_their_rows_are_stored_then_deleted(self):
        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        svc._status_by_job = {}
        svc.emit_event = mock.Mock()
        svc._set_status = mock.Mock()
        svc._running_jobs = set()
        job = scraper.ScrapeJob(job_id="jf", intent=_intent("debates between 2010 to 2025"), table_schema={"columns": ["title", "date", "source_url"], "column_labels": ["Title", "Date", "Source"]})
        plan = ScrapePlan(source_name="Repo", entry_url="https://repo.test/r", source_url="https://repo.test/r",
                          dataset_files=["https://repo.test/a.xlsx", "https://repo.test/b.csv"])
        files = {"https://repo.test/a.xlsx": _xlsx([["Title", "Date"], ["Debate A", "2015-03-01"], ["Debate Z", "2026-01-01"]])}

        def fake_safe_get(url, **kw):
            if url in files:
                return mock.Mock(status_code=200, content=files[url])
            return mock.Mock(status_code=404, content=b"")

        failures = []
        with mock.patch("url_guard.safe_get", side_effect=fake_safe_get), \
                mock.patch("reasoning.gemini_json", return_value={"mapping": {"title": ["Title"], "date": ["Date"]}}), \
                mock.patch.object(scraper.url_access, "record_failure", side_effect=lambda *a, **k: failures.append((a, k))):
            rows = svc._listing_rows(plan, job)
            held = list(os.listdir(self._dir.name))
            with mock.patch.object(svc, "store_record", return_value=None) as store, mock.patch.object(svc, "is_job_live", return_value=False):
                svc._store_rows(plan, job, rows)
        self.assertEqual([r["title"] for r in rows], ["Debate A"], "the 2026 row is outside the period, dropped before any cap")
        self.assertEqual(rows[0]["source_url"], "https://repo.test/a.xlsx")
        self.assertEqual(len(held), 1, "the downloaded file exists while its rows wait to be stored")
        self.assertEqual(os.listdir(self._dir.name), [], "and is deleted once they are stored")
        self.assertEqual([c.args[2]["title"] for c in store.call_args_list], ["Debate A"])
        self.assertEqual(failures[0][1]["outcome"], "error")
        self.assertIn("HTTP 404", failures[0][1]["reason"])

    def test_a_data_file_found_by_search_is_a_source_and_a_page_with_files_is_accepted(self):
        import inspector

        with mock.patch.object(inspector, "probe_https", return_value={"https_ok": True, "http_status": 200, "final_url": "https://raw.test/d.csv"}), \
                mock.patch.object(inspector.url_access, "record_probe"):
            plan = inspector.inspect_source(_intent("x"), inspector.SourceCandidate(url="https://raw.test/d.csv", domain="raw.test"))
        self.assertEqual(plan.dataset_files, ["https://raw.test/d.csv"])
        self.assertFalse(plan.blocked)
        page = ScrapePlan(source_name="Zenodo", entry_url="https://z.test", dataset_files=["https://z.test/f.xlsx"])
        self.assertIsNone(inspector.inspection_reject_reason(page, https_probe={"http_status": 200, "https_ok": True}, signals={}))
        self.assertEqual(ScrapePlan.from_dict(page.to_dict()).dataset_files, ["https://z.test/f.xlsx"])


if __name__ == "__main__":
    unittest.main()
