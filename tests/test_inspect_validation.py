"""Discovery must reject missing pages and empty dry-runs."""

from __future__ import annotations

import unittest

from inspector import ScrapePlan, inspection_reject_reason, page_looks_unreachable


class InspectValidationTests(unittest.TestCase):
    def test_http_404_rejected(self) -> None:
        self.assertEqual(page_looks_unreachable(http_status=404, title="OK"), "HTTP 404 (page not found)")

    def test_not_found_title_rejected(self) -> None:
        self.assertIsNotNone(page_looks_unreachable(http_status=200, title="404 Not Found"))

    def test_zero_rows_no_tables_rejected(self) -> None:
        plan = ScrapePlan(source_name="X", entry_url="https://example.org", dry_run_rows=0)
        reason = inspection_reject_reason(
            plan,
            https_probe={"https_ok": True, "http_status": 200, "table_count": 0, "table_headers_preview": []},
            signals={"title": "Sessions", "tables": []},
        )
        self.assertEqual(reason, "No table/list data detected (dry-run 0 rows)")

    def test_probe_tables_allow_zero_dry_run(self) -> None:
        plan = ScrapePlan(source_name="X", entry_url="https://example.org", dry_run_rows=0)
        reason = inspection_reject_reason(
            plan,
            https_probe={
                "https_ok": True,
                "http_status": 200,
                "table_count": 2,
                "table_headers_preview": ["Session", "Dates"],
            },
            signals={"title": "Sessions", "tables": []},
        )
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
