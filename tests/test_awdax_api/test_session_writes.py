"""Background writers save only what they changed, so a late live event cannot erase a finished run."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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


class LateLiveEventTests(unittest.TestCase):
    """A live event (a saved row, a log line) that loaded the chat before the run's final save used to write that stale
    copy back after it, erasing the intent, schema, plans, research and the "Run complete" message."""

    def setUp(self):
        import ui_sessions

        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._dir.cleanup)
        db = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "s.sqlite")
        db.start()
        self.addCleanup(db.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        self.ui = ui_sessions

    def test_a_late_event_keeps_the_final_save_and_its_status(self):
        import importlib

        lb = importlib.import_module("awdax_api.live_bridge")  # the package exports the bridge object under this name
        from awdax_api.session_store import append_message, load_instance_session, persist_run_state, set_awdax_run

        sess = self.ui.create_session(user_id="u1", title="t")
        iid = sess["id"]
        set_awdax_run(sess, status="running", phase="extracting")
        sess["run_active"] = True
        persist_run_state(sess)
        stale = load_instance_session(iid)  # what a row event loaded mid-run

        final = load_instance_session(iid)
        final.update(research={"websites": [{"rank": 1}]}, plans=[{"source_name": "RS"}], run_active=False)
        append_message(final, role="assistant", content="Run complete.")
        set_awdax_run(final, status="succeeded", phase="complete", detail="First pass complete")
        persist_run_state(final)

        bridge = lb.LiveBridge.__new__(lb.LiveBridge)
        bridge.notify_instance = lambda *a, **k: None
        bridge._resolve_instance = lambda event, channel: iid
        with mock.patch.object(lb, "load_instance_session", return_value=stale):
            bridge._handle_backend_event({"type": "log", "message": "late line"}, "universal")
        after = load_instance_session(iid)
        self.assertEqual(after["research"], {"websites": [{"rank": 1}]})
        self.assertEqual(after["plans"], [{"source_name": "RS"}])
        self.assertEqual([m["content"] for m in after["messages"]], ["Run complete."])
        self.assertEqual((after["awdax_run"]["status"], after["awdax_run"]["detail"]), ("succeeded", "First pass complete"))

    def test_progress_during_a_run_still_shows(self):
        from awdax_api import orchestrator
        from awdax_api.session_store import load_instance_session

        iid = self.ui.create_session(user_id="u1", title="t")["id"]
        with mock.patch.object(orchestrator.live_bridge, "notify_instance"):
            orchestrator._on_progress(iid, "discovery", "Searching…")
            orchestrator._on_source(iid, {"url": "https://a.test", "status": "validated", "origin": "research"})
            orchestrator._on_job(iid, "job9")
        after = load_instance_session(iid)
        self.assertEqual((after["awdax_run"]["phase"], after["awdax_run"]["detail"]), ("discovery", "Searching…"))
        self.assertEqual(after["run_events"][-1]["detail"], "Searching…")
        self.assertEqual([s["origin"] for s in after["discovery_sources"]], ["research"])
        self.assertEqual(after["job_id"], "job9")
        self.assertIsNone(orchestrator.update_instance("gone", lambda s: None))


if __name__ == "__main__":
    unittest.main()
