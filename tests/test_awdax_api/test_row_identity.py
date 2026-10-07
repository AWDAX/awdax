"""Rows that share a date or an id on one page stay separate; the same item from two sources merges."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from inspector import ScrapePlan  # noqa: E402
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


class RowIdentityTests(unittest.TestCase):
    COLS = ["date", "house", "debate_title", "subject", "source_url"]

    def _rows(self):
        return [
            {"date": "2025-02-04", "house": "Rajya Sabha", "debate_title": f"Matter {i}", "subject": "MATTERS RAISED WITH PERMISSION"}
            for i in range(4)
        ] + [{"date": "2025-02-07", "house": "Rajya Sabha", "debate_title": "The Virtual Court Proceedings Bill, 2024", "subject": "BILLS"}]

    def test_rows_sharing_a_date_on_one_page_keep_their_own_ids(self):
        from listing_extract import _finalize_extract_rows

        plan = ScrapePlan(source_name="RS", entry_url="https://s.test", id_field="row_index")
        rows = _finalize_extract_rows(self._rows(), plan, intent=_intent(), columns=self.COLS)
        self.assertEqual(len(rows), 5)
        uids = [r.get("_uid") for r in rows[:4]]
        self.assertEqual(len(set(uids)), 4, "four debates of one sitting are four rows")
        self.assertNotIn("_uid", rows[4], "a row whose id is already unique keeps it")

    def test_the_store_keys_on_the_unique_id(self):
        import scraper

        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        plan = ScrapePlan(source_name="RS", entry_url="https://s.test", id_field="row_index")
        keys = []

        class Cur:
            def execute(self, sql, args=()):
                if sql.lstrip().startswith("INSERT"):
                    keys.append(args[2])

            def fetchone(self):
                return None

            def close(self):
                pass

        conn = mock.Mock(cursor=mock.Mock(return_value=Cur()))
        with mock.patch.object(scraper, "_get_db", return_value=conn), mock.patch.object(scraper, "init_universal_tables"):
            for i in range(3):
                svc.store_record("job", "https://s.test/x", {"row_index": "2025-02-04", "_uid": f"2025-02-04|{i}"}, plan)
        self.assertEqual(keys, ["s.test:2025-02-04|0", "s.test:2025-02-04|1", "s.test:2025-02-04|2"])

    def test_merging_keeps_one_pages_rows_apart_and_never_merges_on_a_date(self):
        from table_merge import merge_records

        records = [{"data": r, "source_url": "https://rs.test/debates"} for r in self._rows()]
        records.append({"data": {"date": "2025-02-04", "house": "Lok Sabha", "debate_title": "Question on railways", "subject": "Q&A"}, "source_url": "https://ls.test/qa"})
        records.append({"data": dict(self._rows()[0]), "source_url": "https://rs.test/debates"})  # an exact repeat
        out = merge_records(_intent(), records, use_ai=False, columns_override=self.COLS)
        self.assertEqual(out["row_count"], 6, "5 debates + 1 Lok Sabha row; the exact repeat merges")

    def test_one_final_written_by_two_sites_is_one_row_but_two_debates_of_one_day_stay_two(self):
        from table_merge import merge_records

        cols = ["year", "host_country", "winner", "score", "runner_up"]
        finals = [
            {"data": {"year": "2010", "host_country": "South Africa", "winner": "Spain", "score": "1–0 ( a.e.t. )", "runner_up": "Netherlands"}, "source_url": "https://wiki.test"},
            {"data": {"year": "2006", "host_country": "Germany", "winner": "Italy", "score": "1–1 (5–3 p)", "runner_up": "France"}, "source_url": "https://wiki.test"},
            {"data": {"year": "2010", "host_country": "South Africa", "winner": "Spain", "score": "Spain 1-0 Netherlands", "runner_up": "Netherlands"}, "source_url": "https://other.test"},
            {"data": {"year": "2006", "host_country": "Germany", "winner": "Italy", "score": "1-1, then Italy beat France 5-3 on penalties", "runner_up": "France"}, "source_url": "https://other.test"},
        ]
        out = merge_records(_intent("World Cup finals 1990 to 2010"), finals, use_ai=False, columns_override=cols)
        self.assertEqual(sorted(r["year"] for r in out["rows"]), ["2006", "2010"])
        debates = [
            {"data": {"date": "2025-02-04", "house": "Rajya Sabha", "debate_title": "Need to enhance the potential of National Waterways", "subject": "MATTERS RAISED"}, "source_url": "https://rs.test"},
            {"data": {"date": "2025-02-04", "house": "Rajya Sabha", "debate_title": "Concern over unlawful detention of Indian emigrants", "subject": "MATTERS RAISED"}, "source_url": "https://mirror.test"},
            {"data": {"date": "2025-02-04", "house": "Rajya Sabha", "debate_title": "Need to enhance the potential of National Waterways", "subject": ""}, "source_url": "https://mirror.test"},
        ]
        out = merge_records(_intent("debates 2010 to 2025"), debates, use_ai=False, columns_override=["date", "house", "debate_title", "subject"])
        self.assertEqual(out["row_count"], 2, "the mirror's copy of the waterways debate merges; the other debate of that day does not")

    def test_rows_named_alike_from_two_sources_still_merge(self):
        from table_merge import merge_records

        cols = ["institute_name", "city", "source_url"]
        records = [
            {"data": {"institute_name": "IIT Bombay", "city": "Mumbai"}, "source_url": "https://a.test"},
            {"data": {"institute_name": "IIT Bombay", "city": ""}, "source_url": "https://b.test"},
        ]
        out = merge_records(_intent("list all IITs"), records, use_ai=False, columns_override=cols)
        self.assertEqual(out["row_count"], 1)


if __name__ == "__main__":
    unittest.main()
