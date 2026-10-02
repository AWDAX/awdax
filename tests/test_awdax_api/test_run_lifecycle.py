"""Run lifecycle: deleted chats stay deleted, pause during the first run, Resume/Retry restart work."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_sessions  # noqa: E402
from awdax_api import orchestrator, pipeline_runner  # noqa: E402
from awdax_api.session_store import load_instance_session, persist_session, set_awdax_run  # noqa: E402


class _Base(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        self._patch.start()
        ui_sessions._initialized = None
        self._env = mock.patch.dict(os.environ, {}, clear=True)
        self._env.start()
        import app as app_module

        self.client = app_module.app.test_client()

    def tearDown(self):
        self._env.stop()
        self._patch.stop()
        ui_sessions._initialized = None
        try:
            self._dir.cleanup()
        except OSError:
            pass

    def _create(self, **extra):
        r = self.client.post("/api/instances", json={"title": "t"})
        self.assertEqual(r.status_code, 201)
        iid = r.get_json()["id"]
        if extra:
            sess = load_instance_session(iid)
            sess.update(extra)
            persist_session(sess)
        return iid


class DeletedChatStaysDeletedTests(_Base):
    def test_background_writers_do_not_resurrect_a_deleted_chat(self):
        iid = self._create()
        old = load_instance_session(iid)
        self.assertEqual(self.client.delete(f"/api/instances/{iid}").status_code, 204)

        out = persist_session(old)
        self.assertEqual(out["id"], iid)
        with mock.patch.object(orchestrator.live_bridge, "notify_instance"):
            orchestrator._on_progress(iid, "planning", "x")
            orchestrator._on_source(iid, {"url": "http://a"})
            orchestrator._on_job(iid, "job1")
        orchestrator.unregister_job(iid, "job1")

        self.assertEqual(self.client.get(f"/api/instances/{iid}").status_code, 404)
        self.assertNotIn(iid, [i["id"] for i in self.client.get("/api/instances").get_json()])

    def test_new_chat_still_inserts(self):
        iid = self._create()
        self.assertEqual(self.client.get(f"/api/instances/{iid}").status_code, 200)
        fresh = {"id": "newid1", "title": "n", "user_id": "anonymous"}
        ui_sessions.save_session(fresh)
        self.assertIsNotNone(ui_sessions.get_session("newid1"))

    def test_run_thread_stops_live_job_when_chat_deleted_mid_run(self):
        iid = self._create()

        def fake_pipeline(s, goal, **kw):
            s["job_id"] = "jobX"
            ui_sessions.delete_session(iid)
            return s

        with mock.patch.object(orchestrator, "run_pipeline_for_session", side_effect=fake_pipeline), \
                mock.patch.object(orchestrator.live_bridge, "notify_instance") as notify, \
                mock.patch.object(orchestrator.universal_service, "stop_live") as stop:
            orchestrator.mark_running(iid)
            orchestrator._run_thread(iid, "goal", None)
        stop.assert_called_once_with("jobX")
        notify.assert_not_called()
        self.assertIsNone(ui_sessions.get_session(iid))
        self.assertFalse(orchestrator.is_running(iid))


class PauseDuringFirstRunTests(_Base):
    def _run(self, stored_live):
        iid = self._create(keep_live=stored_live)
        sess = load_instance_session(iid)
        sess["keep_live"] = True  # stale copy held by the run thread
        return iid, sess

    def _drive(self, sess):
        plan = mock.MagicMock()
        plan.to_dict.return_value = {}
        intent = mock.MagicMock(job_id="j1")
        intent.to_dict.return_value = {}
        pr = pipeline_runner
        with mock.patch.object(pr, "parse_prompt", return_value=intent), \
                mock.patch.object(pr, "generate_search_queries", return_value=[]), \
                mock.patch.object(pr, "discover_inspected_sources", return_value=([], [plan])), \
                mock.patch.object(pr, "intent_uses_regulatory_feed", return_value=False), \
                mock.patch.object(pr, "ScrapeJob"), \
                mock.patch("table_schema.propose_table_schema", return_value=None), \
                mock.patch.object(pr.universal_service, "clear_job_dataset"), \
                mock.patch.object(pr.universal_service, "save_job"), \
                mock.patch.object(pr.universal_service, "trigger_scrape_all") as trigger:
            try:
                pr.run_pipeline_for_session(sess, "goal")
            finally:
                self.trigger = trigger

    def test_pause_made_during_discovery_is_honoured(self):
        iid, sess = self._run(False)
        self._drive(sess)
        self.trigger.assert_called_once()
        self.assertIs(self.trigger.call_args.kwargs["live"], False)

    def test_still_live_when_not_paused(self):
        iid, sess = self._run(True)
        self._drive(sess)
        self.assertIs(self.trigger.call_args.kwargs["live"], True)

    def test_deleted_chat_raises_and_does_not_scrape(self):
        iid, sess = self._run(True)
        ui_sessions.delete_session(iid)
        with self.assertRaises(pipeline_runner.InstanceDeleted):
            self._drive(sess)
        self.trigger.assert_not_called()

    def test_run_thread_quietly_ignores_instance_deleted(self):
        iid = self._create()
        with mock.patch.object(orchestrator, "run_pipeline_for_session", side_effect=pipeline_runner.InstanceDeleted(iid)), \
                mock.patch.object(orchestrator.live_bridge, "notify_instance") as notify:
            orchestrator.mark_running(iid)
            orchestrator._run_thread(iid, "goal", None)
        notify.assert_not_called()
        after = load_instance_session(iid)
        self.assertFalse([m for m in after["messages"] if "Run failed" in m["content"]])


class ResumeTests(_Base):
    def _patch_all(self, running=False, live=False):
        return (
            mock.patch.object(orchestrator, "is_running", return_value=running),
            mock.patch.object(orchestrator, "start_run"),
            mock.patch.object(orchestrator.universal_service, "start_live"),
            mock.patch.object(orchestrator.universal_service, "is_job_live", return_value=live),
        )

    def _call(self, iid, patcher_args, path="live", body=None):
        body = body if body is not None else {"enabled": True}
        p1, p2, p3, p4 = patcher_args
        with p1, p2 as start_run, p3 as start_live, p4:
            if path == "live":
                r = self.client.patch(f"/api/instances/{iid}/live", json=body)
            else:
                r = self.client.patch(f"/api/instances/{iid}", json=body)
            self.assertEqual(r.status_code, 200)
            return start_run, start_live

    def _completed_fields(self):
        return {
            "job_id": "j1",
            "goal": "g",
            "intent": {"job_id": "j1", "topic": "t"},
            "plans": [{"url": "http://a"}],
            "messages": [],
        }

    def test_failed_run_with_goal_restarts_run(self):
        iid = self._create(goal="find things", **{k: v for k, v in self._completed_fields().items() if k != "goal"})
        sess = load_instance_session(iid)
        set_awdax_run(sess, status="failed", phase="failed")
        persist_session(sess)
        start_run, start_live = self._call(iid, self._patch_all())
        start_run.assert_called_once_with(iid, "find things")
        start_live.assert_not_called()

    def test_completed_run_not_live_starts_live(self):
        iid = self._create(**self._completed_fields())
        sess = load_instance_session(iid)
        set_awdax_run(sess, status="succeeded", phase="complete")
        persist_session(sess)
        with mock.patch.object(orchestrator, "_job_from_session", return_value=(["plan"], "job")):
            start_run, start_live = self._call(iid, self._patch_all(), path="instance", body={"live_enabled": True})
        start_live.assert_called_once_with(["plan"], "job")
        start_run.assert_not_called()

    def test_completed_run_already_live_does_nothing(self):
        iid = self._create(**self._completed_fields())
        start_run, start_live = self._call(iid, self._patch_all(live=True))
        start_run.assert_not_called()
        start_live.assert_not_called()

    def test_goal_without_messages_appends_user_message_and_runs(self):
        iid = self._create(goal="scrape x")
        start_run, _ = self._call(iid, self._patch_all())
        start_run.assert_called_once_with(iid, "scrape x")
        msgs = load_instance_session(iid)["messages"]
        self.assertEqual([(m["role"], m["content"]) for m in msgs], [("user", "scrape x")])

    def test_already_running_does_nothing(self):
        iid = self._create(goal="scrape x")
        start_run, start_live = self._call(iid, self._patch_all(running=True))
        start_run.assert_not_called()
        start_live.assert_not_called()

    def test_disable_does_nothing(self):
        iid = self._create(goal="scrape x")
        for path, body in (("live", {"enabled": False}), ("instance", {"live_enabled": False})):
            start_run, start_live = self._call(iid, self._patch_all(), path=path, body=body)
            start_run.assert_not_called()
            start_live.assert_not_called()
        self.assertFalse(load_instance_session(iid)["keep_live"])

    def test_no_goal_does_nothing(self):
        iid = self._create()
        start_run, start_live = self._call(iid, self._patch_all())
        start_run.assert_not_called()
        start_live.assert_not_called()

    def test_start_run_already_running_error_is_ignored(self):
        iid = self._create(goal="scrape x")
        p = self._patch_all()
        with p[0], p[1] as sr, p[2], p[3]:
            sr.side_effect = RuntimeError("already")
            r = self.client.patch(f"/api/instances/{iid}/live", json={"enabled": True})
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
