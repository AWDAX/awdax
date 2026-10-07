"""The plain request every link gets first, and the per-run list of links that failed it."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import inspector  # noqa: E402
import url_access  # noqa: E402
from discovery import SourceCandidate  # noqa: E402
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


class _TempDb(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        env = mock.patch.dict(os.environ, {"SQLITE_PATH": str(Path(self._dir.name) / "t.sqlite")})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._dir.cleanup)
        url_access._ready = False
        self.addCleanup(setattr, url_access, "_ready", False)
        import RegulatoryFeed

        initialized = mock.patch.object(RegulatoryFeed, "_DB_INITIALIZED", False)
        initialized.start()
        self.addCleanup(initialized.stop)


class PlainRequestTests(_TempDb):
    def test_outcomes(self):
        cases = [
            ({"http_status": 403, "https_ok": True}, "blocked"),
            ({"http_status": 429}, "blocked"),
            ({"http_status": 404}, "not found"),
            ({"http_status": 503}, "error"),
            ({"http_status": 0, "error": "could not resolve host"}, "unreachable"),
            ({"blocked": True, "error": "private address"}, "not allowed"),
            ({"http_status": 200, "https_ok": True, "html": '<div class="g-recaptcha"></div>'}, "captcha"),
        ]
        for probe, outcome in cases:
            self.assertEqual(url_access.classify(probe)[0], outcome, probe)
        self.assertIsNone(url_access.classify({"http_status": 200, "https_ok": True, "html": "<p>" + "text " * 500}))

    def test_failures_become_a_dataset_one_row_per_link(self):
        url_access.record_probe("job1", "https://a.test/x", {"http_status": 403, "https_ok": True}, stage="research")
        url_access.record_probe("job1", "https://a.test/x", {"http_status": 0}, stage="inspect")  # the same link again: first failure kept
        url_access.record_probe("job1", "https://b.test/y", {"http_status": 200, "https_ok": True}, stage="search")  # answered: not kept
        url_access.record_probe("job2", "https://c.test/z", {"http_status": 404}, stage="scrape")
        table = url_access.dataset_for_job("job1")
        self.assertEqual(table["columns"], url_access.COLUMNS)
        self.assertEqual(table["row_count"], 1)
        row = table["rows"][0]
        self.assertEqual((row["url"], row["domain"], row["stage"], row["outcome"], row["http_status"]), ("https://a.test/x", "a.test", "research", "blocked", 403))
        self.assertEqual(url_access.dataset_for_job("")["rows"], [])

    def test_inspection_records_a_refused_plain_request(self):
        refused = {"https_ok": False, "http_status": 403, "error": "HTTP 403, body=10 bytes", "blocked": False}
        with mock.patch.object(inspector, "probe_https", return_value=refused):
            plan = inspector.inspect_source(_intent(), SourceCandidate(url="https://gov.test/list", domain="gov.test"))
        self.assertTrue(plan.blocked)
        self.assertEqual([r["outcome"] for r in url_access.failures_for_job("job-r")], ["blocked"])


class FailedLinksRouteTests(_TempDb):
    def test_the_chat_returns_its_failed_links_and_research(self):
        import ui_sessions

        db = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "s.sqlite")
        db.start()
        self.addCleanup(db.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        with mock.patch.dict(os.environ, {"AWDAX_AUTH_MODE": "dev"}):
            import app as app_module

            client = app_module.app.test_client()
            iid = client.post("/api/instances", json={}, headers={"X-User-Id": "u1"}).get_json()["id"]
            sess = ui_sessions.get_session(iid, "u1")
            sess["job_id"] = "jobX"
            sess["research"] = {"websites": [{"rank": 1, "url": "https://a.test"}]}
            ui_sessions.save_session(sess)
            url_access.record_failure("jobX", "https://blocked.test/p", stage="research", outcome="blocked", reason="HTTP 403", http_status=403)
            body = client.get(f"/api/instances/{iid}/failed-links", headers={"X-User-Id": "u1"}).get_json()
            other = client.get(f"/api/instances/{iid}/failed-links", headers={"X-User-Id": "u2"})
        self.assertEqual(body["row_count"], 1)
        self.assertEqual(body["rows"][0]["url"], "https://blocked.test/p")
        self.assertEqual(body["research"], [{"rank": 1, "url": "https://a.test"}])
        self.assertEqual(other.status_code, 404)


if __name__ == "__main__":
    unittest.main()
