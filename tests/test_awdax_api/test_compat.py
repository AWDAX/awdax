import unittest

from awdax_api.dataset_export import build_dataset_table, dataset_row_count
from awdax_api.run_report import format_discovery_report
from awdax_api.serializers import to_awdax_instance
from ui_sessions import create_session, delete_session_internal as delete_session


class AwdaxCompatTests(unittest.TestCase):
    def test_instance_serializer(self):
        sess = create_session(title="Hello")
        out = to_awdax_instance(sess)
        self.assertEqual(out["title"], "Hello")
        self.assertIn("dataset_row_count", out)
        delete_session(sess["id"])

    def test_discovery_report_parses_markers(self):
        sess = {
            "sources": [],
            "plans": [{"source_name": "eGazette", "entry_url": "https://egazette.gov.in", "confidence": 1.0}],
            "search_queries": [{"query": "site:egazette.gov.in"}],
            "table_schema": {"columns": ["gazette_id", "subject"]},
        }
        text = format_discovery_report(sess, goal="latest egazette")
        self.assertIn("=== AWDAX SOURCE DISCOVERY ===", text)
        self.assertIn("VALIDATED SOURCES", text)

    def test_empty_dataset(self):
        sess = create_session(title="Empty")
        table = build_dataset_table(sess)
        self.assertTrue(table is None or table.get("row_count", 0) == 0)
        self.assertEqual(dataset_row_count(sess), 0)
        delete_session(sess["id"])


if __name__ == "__main__":
    unittest.main()
