"""A "list all ..." request that is not about cars is no longer treated as an EV price catalog."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import query_generation  # noqa: E402
import row_quality  # noqa: E402
from reasoning import ScrapeIntent  # noqa: E402
from table_merge import merge_records  # noqa: E402


def _intent(prompt, topic=None):
    return ScrapeIntent(job_id="j", topic=topic or prompt, raw_prompt=prompt)


class QueryBiasTests(unittest.TestCase):
    def test_a_non_car_list_request_never_gets_ev_fallback_queries(self):
        intent = _intent("list all dental clinics in pune")
        out = query_generation._fallback_queries(intent.raw_prompt, 6, set(), intent)
        joined = " ".join(q.query for q in out).lower()
        self.assertTrue(out)
        for word in ("electric", "cardekho", "carwale", "91wheels", "ev "):
            self.assertNotIn(word, joined)
        self.assertIn("dental clinics in pune", joined)

    def test_an_ev_request_keeps_its_ev_queries(self):
        intent = _intent("list all EV cars with prices")
        out = query_generation._fallback_queries(intent.raw_prompt, 4, set(), intent)
        self.assertTrue(any("electric" in q.query.lower() for q in out))

    def test_the_purpose_text_for_other_topics_does_not_ask_for_models_and_prices(self):
        text = query_generation._purpose_block("list all dental clinics in pune", _intent("list all dental clinics in pune"))
        self.assertNotIn("model", text.lower())
        self.assertNotIn("prices/specs", text)
        self.assertIn("COMPLETE list", text)

    def test_a_car_brand_only_narrows_a_car_catalog(self):
        self.assertFalse(query_generation._is_narrow_query("tata motors authorised dealers list"))
        self.assertTrue(query_generation._is_narrow_query("tata electric cars", car_brands=True))
        self.assertTrue(query_generation._is_narrow_query("best clinics in pune"))

    def test_generated_queries_for_a_brand_named_list_are_kept(self):
        intent = _intent("list all tata motors dealers in india")
        with mock.patch("query_generation.gemini_json", return_value=["tata motors dealers india list", "tata motors showroom directory"]):
            out = query_generation.generate_search_queries(intent, count=2)
        self.assertEqual([q.query for q in out], ["tata motors dealers india list", "tata motors showroom directory"])


class RowQualityTests(unittest.TestCase):
    LONG = "Sharma Dental Care and Orthodontic Implant Centre Pune Branch"

    def test_a_long_business_name_is_kept_for_a_non_vehicle_topic(self):
        self.assertTrue(row_quality.is_valid_vehicle_row({"name": self.LONG}, vehicle=False))
        self.assertFalse(row_quality.is_valid_vehicle_row({"name": self.LONG}, vehicle=True))

    def test_question_navigation_and_url_names_are_junk_for_any_topic(self):
        for name in ("Which is the best clinic in Pune?", "View all", "https://example.com/clinic"):
            for vehicle in (True, False):
                self.assertFalse(row_quality.is_valid_vehicle_row({"name": name}, vehicle=vehicle), (name, vehicle))

    def test_long_titles_and_question_word_openers_are_kept_unless_the_topic_is_vehicles(self):
        quote = "Do not go gentle into that good night, rage, rage against the dying of the light, and do not stop " + "x" * 80
        debate = "Need to enhance the potential of National Waterways and to expedite the construction of the overbridge near the temple"
        for name in (quote, debate, "Where there is love there is life"):
            self.assertTrue(row_quality.is_valid_vehicle_row({"name": name}, vehicle=False), name)
        self.assertFalse(row_quality.is_valid_vehicle_row({"name": quote}, vehicle=True))
        self.assertFalse(row_quality.is_valid_vehicle_row({"name": "Which is the best clinic in Pune"}, vehicle=True))

    def test_finalized_rows_of_a_non_vehicle_request_keep_long_titles(self):
        from inspector import ScrapePlan
        from listing_extract import _finalize_extract_rows

        intent = _intent("list the quotes with their author", "quotes")
        rows = [{"quote": "Do not go gentle into that good night, rage, rage against the dying of the light and more " * 2, "author": "D. Thomas"}]
        plan = ScrapePlan(source_name="q", entry_url="https://q.test", id_field="quote")
        self.assertEqual(len(_finalize_extract_rows(rows, plan, intent=intent, columns=["quote", "author"])), 1)

    def test_vehicle_topic_detection(self):
        self.assertTrue(row_quality.topic_is_vehicles("list all EV cars", ""))
        self.assertTrue(row_quality.topic_is_vehicles("", "electric scooters"))
        self.assertFalse(row_quality.topic_is_vehicles("local business leads in delhi ncr for web development", ""))
        self.assertFalse(row_quality.topic_is_vehicles("review centres in pune", ""))  # "review" is not a vehicle word

    def test_merge_keeps_long_named_rows_for_a_non_vehicle_intent(self):
        intent = _intent("list all dental clinics in pune", "dental clinics")
        records = [{"source_url": "https://x.test/a", "data": {"name": self.LONG, "value": "4.8"}}]
        table = merge_records(intent, records, use_ai=False)
        self.assertEqual([r["name"] for r in table["rows"]], [self.LONG])


if __name__ == "__main__":
    unittest.main()
