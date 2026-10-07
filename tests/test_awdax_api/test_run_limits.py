"""BE-06 a new message stops the previous live loop; BE-07 caps on concurrent runs."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ui_sessions  # noqa: E402
from awdax_api import orchestrator, routes, run_registry  # noqa: E402
from awdax_api.session_store import load_instance_session, persist_session  # noqa: E402
from test_run_lifecycle import _Base  # noqa: E402

LIMIT_DETAIL = "Too many runs are active right now. Please try again in a few minutes."


class _RegistryBase(_Base):
    def setUp(self):
        super().setUp()
        self._reset_registry()
        self.addCleanup(self._reset_registry)

    @staticmethod
    def _reset_registry():
        with run_registry._lock:
            run_registry._running.clear()
            if hasattr(run_registry, "_owners"):
                run_registry._owners.clear()
            run_registry._queue.clear()
            run_registry._queued.clear()
            run_registry._cancelled.clear()

    def _create_for(self, user_id, **extra):
        sess = ui_sessions.create_session(user_id=user_id, title="t")
        if extra:
            sess.update(extra)
            persist_session(sess)
        return sess["id"]

    def _start(self, iid, goal="g"):
        """start_run with the worker thread replaced so no network code runs."""
        with mock.patch.object(orchestrator.threading, "Thread") as thread:
            orchestrator.start_run(iid, goal)
        return thread


class StopLiveOnNewMessageTests(_Base):
    def _post(self, iid):
        parent = mock.Mock()
        with mock.patch.object(routes.universal_service, "stop_live", parent.stop_live), \
                mock.patch.object(routes.universal_service, "clear_job_dataset", parent.clear), \
                mock.patch.object(routes, "submit_run", parent.start_run):
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "new goal"})
        return r, parent

    def test_previous_live_loop_is_stopped_before_clear_and_start(self):
        iid = self._create(job_id="old-job")
        r, parent = self._post(iid)
        self.assertEqual(r.status_code, 201)
        names = [c[0] for c in parent.mock_calls]
        self.assertEqual(names[:3], ["stop_live", "clear", "start_run"])
        parent.stop_live.assert_called_once_with("old-job")
        parent.clear.assert_called_once_with("old-job")

    def test_chat_without_job_id_does_not_stop_anything(self):
        iid = self._create()
        r, parent = self._post(iid)
        self.assertEqual(r.status_code, 201)
        parent.stop_live.assert_not_called()
        parent.start_run.assert_called_once()

    def test_already_running_rejection_does_not_stop_live_loop(self):
        iid = self._create(job_id="old-job")
        with mock.patch.object(routes, "is_running", return_value=True), \
                mock.patch.object(routes.universal_service, "stop_live") as stop, \
                mock.patch.object(routes.universal_service, "clear_job_dataset") as clear, \
                mock.patch.object(routes, "submit_run") as start:
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "x"})
        self.assertEqual(r.status_code, 409)
        stop.assert_not_called()
        clear.assert_not_called()
        start.assert_not_called()


class WaitingLineTests(_RegistryBase):
    """A run past the limit waits and starts by itself when a slot frees; pausing or deleting frees a slot at once."""

    def _submit(self, iid, goal="g"):
        with mock.patch.object(orchestrator.threading, "Thread") as thread:
            return orchestrator.submit_run(iid, goal), thread

    def test_waiting_runs_start_in_order_as_slots_free_up(self):
        os.environ["AWDAX_MAX_RUNS"] = "2"
        ids = [self._create_for(f"u{i}") for i in range(4)]
        self.assertEqual([self._submit(i)[0] for i in ids], ["started", "started", "queued", "queued"])
        self.assertEqual([run_registry.queue_position(i) for i in ids[2:]], [1, 2])
        run_registry.mark_stopped(ids[0])
        with mock.patch.object(orchestrator.threading, "Thread"):
            self.assertEqual(orchestrator.dispatch_queued(), 1)
        self.assertTrue(run_registry.is_running(ids[2]))
        self.assertFalse(run_registry.is_running(ids[3]))
        self.assertEqual(run_registry.queue_position(ids[3]), 1, "the line moved up")
        self.assertIn("place 1", load_instance_session(ids[3])["awdax_run"]["detail"])

    def test_a_user_at_their_own_limit_does_not_block_others_in_line(self):
        os.environ["AWDAX_MAX_RUNS"] = "3"
        os.environ["AWDAX_MAX_RUNS_PER_USER"] = "1"
        a1, a2, b1 = self._create_for("A"), self._create_for("A"), self._create_for("B")
        self._submit(a1)
        self.assertEqual(self._submit(a2)[0], "queued")
        self.assertEqual(self._submit(b1)[0], "started")
        with mock.patch.object(orchestrator.threading, "Thread"):
            self.assertEqual(orchestrator.dispatch_queued(), 0, "A still has a run going")
        run_registry.mark_stopped(a1)
        with mock.patch.object(orchestrator.threading, "Thread"):
            self.assertEqual(orchestrator.dispatch_queued(), 1)
        self.assertTrue(run_registry.is_running(a2))

    def test_pausing_a_waiting_chat_takes_it_out_of_the_line(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        first, second = self._create_for("A"), self._create_for("B")
        self._submit(first)
        self._submit(second)
        self.assertEqual(orchestrator.cancel_run(second), "queued")
        self.assertIsNone(run_registry.queue_position(second))
        stored = load_instance_session(second)
        self.assertEqual((stored["awdax_run"]["status"], stored["run_active"]), ("cancelled", False))
        run_registry.mark_stopped(first)
        with mock.patch.object(orchestrator.threading, "Thread"):
            self.assertEqual(orchestrator.dispatch_queued(), 0, "nothing is left waiting")

    def test_pausing_a_running_chat_stops_it_and_frees_its_slot_for_the_next(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        first, second = self._create_for("A"), self._create_for("B")
        self._submit(first)
        self._submit(second)
        self.assertEqual(orchestrator.cancel_run(first), "running")
        self.assertTrue(run_registry.is_cancelled(first))
        with self.assertRaises(run_registry.RunCancelled):
            orchestrator._on_progress(first, "discovery", "next step")  # the run unwinds at its next step
        with self.assertRaises(run_registry.RunCancelled):
            orchestrator._on_source(first, {"url": "https://x.test"})
        orchestrator._finish_paused(first)
        self.assertEqual(load_instance_session(first)["awdax_run"]["status"], "cancelled")
        run_registry.mark_stopped(first)  # what the run's `finally` does
        self.assertFalse(run_registry.is_cancelled(first))
        with mock.patch.object(orchestrator.threading, "Thread"):
            self.assertEqual(orchestrator.dispatch_queued(), 1)
        self.assertTrue(run_registry.is_running(second))
        self.assertEqual(orchestrator.cancel_run(self._create_for("C")), "idle")

    def test_the_scrape_stops_at_its_next_row_and_source_when_cancelled(self):
        from awdax_api.run_registry import RunCancelled  # noqa: F401
        import scraper

        svc = scraper.UniversalScrapeService.__new__(scraper.UniversalScrapeService)
        svc._status_by_job = {}
        svc._running_jobs = set()
        svc._live = {}
        svc._set_status = mock.Mock()
        svc.emit_event = mock.Mock()
        job = scraper.ScrapeJob(job_id="j-c", intent=None, table_schema={})
        plan = scraper.ScrapePlan(source_name="s", entry_url="https://s.test")
        seen = []
        svc._on_row = lambda p, j, row, conn=None: (seen.append(row), svc.cancel_job("j-c") if len(seen) == 2 else None)
        svc._store_rows(plan, job, [{"n": i} for i in range(5)])
        self.assertEqual(len(seen), 2, "rows after the pause are not stored")
        self.assertEqual(svc._listing_rows(plan, job), [])
        svc._clear_cancel("j-c")
        self.assertFalse(svc.is_cancelled("j-c"))

    def test_resume_sends_a_stopped_chat_through_the_line(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        run_registry.mark_running("busy-chat")
        iid = self._create_for("A", goal="find things")
        from awdax_api.session_store import set_awdax_run

        sess = load_instance_session(iid)
        set_awdax_run(sess, status="cancelled", phase="cancelled", detail="Paused")
        persist_session(sess)
        with mock.patch.object(orchestrator.threading, "Thread"):
            orchestrator.resume_instance(iid, load_instance_session(iid))
        self.assertEqual(run_registry.queue_position(iid), 1, "it waits instead of silently not running")
        orchestrator.resume_instance(iid, load_instance_session(iid))
        self.assertEqual(run_registry.queued_ids().count(iid), 1)

    def test_pause_and_delete_through_the_api_stop_the_run(self):
        os.environ["AWDAX_MAX_RUNS"] = "2"
        iid = self._create(goal="g")
        self._start(iid)
        with mock.patch.object(routes, "cancel_run", wraps=orchestrator.cancel_run) as cancel:
            self.client.patch(f"/api/instances/{iid}/live", json={"enabled": False})
            self.assertTrue(run_registry.is_cancelled(iid))
            self.client.delete(f"/api/instances/{iid}")
        self.assertEqual(cancel.call_count, 2)


class RunLimitTests(_RegistryBase):
    def test_global_cap_blocks_next_start_run(self):
        os.environ["AWDAX_MAX_RUNS"] = "2"
        ids = [self._create_for(f"u{i}") for i in range(3)]
        self._start(ids[0])
        self._start(ids[1])
        with self.assertRaises(run_registry.RunLimitError):
            self._start(ids[2])
        self.assertFalse(run_registry.is_running(ids[2]))

    def test_default_global_cap_is_ten(self):
        ids = [self._create_for(f"u{i}") for i in range(11)]
        for iid in ids[:10]:
            self._start(iid)
        with self.assertRaises(run_registry.RunLimitError):
            self._start(ids[10])

    def test_a_request_at_the_cap_waits_in_line_instead_of_being_refused(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        run_registry.mark_running("someone-else")
        iid = self._create()
        with mock.patch.object(orchestrator.threading, "Thread"):
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "hello"})
        self.assertEqual(r.status_code, 201)
        self.assertFalse(run_registry.is_running(iid))
        self.assertEqual(run_registry.queue_position(iid), 1)
        stored = load_instance_session(iid)
        self.assertEqual([m["content"] for m in stored["messages"]], ["hello"], "the request is saved, so it can start later")
        self.assertEqual((stored["awdax_run"]["phase"], stored["run_active"]), ("queued", True))
        self.assertIn("Waiting for a free slot", stored["awdax_run"]["detail"])

    def test_only_a_full_waiting_list_gives_429_and_has_no_side_effects(self):
        """429 comes before anything is stopped, cleared or saved: a user turned away keeps their tracking and data."""
        os.environ["AWDAX_MAX_RUNS"] = "1"
        os.environ["AWDAX_MAX_QUEUE"] = "1"
        run_registry.mark_running("someone-else")
        run_registry.enqueue("another-waiting-chat", "B", {"goal": "g"})
        iid = self._create()
        sess = load_instance_session(iid)
        sess.update(job_id="job-1", title="Keep me")
        persist_session(sess)
        with mock.patch.object(routes.universal_service, "stop_live") as stop, \
                mock.patch.object(routes.universal_service, "clear_job_dataset") as clear, \
                mock.patch.object(orchestrator.threading, "Thread"):
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "a new request"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.get_json()["detail"], LIMIT_DETAIL)
        stop.assert_not_called()
        clear.assert_not_called()
        stored = load_instance_session(iid)
        self.assertEqual(stored["title"], "Keep me")
        self.assertEqual([m for m in stored.get("messages") or [] if m.get("content") == "a new request"], [])

    def test_per_user_cap_applies_per_user_only(self):
        os.environ["AWDAX_MAX_RUNS_PER_USER"] = "2"
        a = [self._create_for("A") for _ in range(3)]
        b = self._create_for("B")
        self._start(a[0])
        self._start(a[1])
        with self.assertRaises(run_registry.RunLimitError):
            self._start(a[2])
        self._start(b)  # user B is unaffected
        self.assertTrue(run_registry.is_running(b))

    def test_default_per_user_cap_is_five(self):
        a = [self._create_for("A") for _ in range(6)]
        for iid in a[:5]:
            self._start(iid)
        with self.assertRaises(run_registry.RunLimitError):
            self._start(a[5])

    def test_mark_stopped_releases_the_slot(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        first, second = self._create_for("A"), self._create_for("B")
        self._start(first)
        with self.assertRaises(run_registry.RunLimitError):
            self._start(second)
        run_registry.mark_stopped(first)
        self._start(second)
        self.assertTrue(run_registry.is_running(second))

    def test_mark_stopped_releases_the_per_user_slot(self):
        os.environ["AWDAX_MAX_RUNS_PER_USER"] = "1"
        first, second = self._create_for("A"), self._create_for("A")
        self._start(first)
        with self.assertRaises(run_registry.RunLimitError):
            self._start(second)
        run_registry.mark_stopped(first)
        self._start(second)

    def test_same_instance_twice_is_runtime_error_not_limit_error(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        iid = self._create_for("A")
        self._start(iid)
        with self.assertRaises(RuntimeError) as ctx:
            self._start(iid)
        self.assertNotIsInstance(ctx.exception, run_registry.RunLimitError)

    def test_run_limit_error_is_not_a_runtime_error(self):
        self.assertFalse(issubclass(run_registry.RunLimitError, RuntimeError))

    def test_same_instance_twice_is_409_even_when_cap_reached(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        iid = self._create()
        self._start(iid)
        with mock.patch.object(orchestrator.threading, "Thread"):
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "again"})
        self.assertEqual(r.status_code, 409)

    def test_try_mark_running_already_running_precedes_limit(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        run_registry.try_mark_running("x", "A")
        with self.assertRaises(RuntimeError) as ctx:
            run_registry.try_mark_running("x", "A")
        self.assertNotIsInstance(ctx.exception, run_registry.RunLimitError)

    def test_env_overrides_are_read_at_call_time(self):
        ids = [self._create_for(f"u{i}") for i in range(3)]
        os.environ["AWDAX_MAX_RUNS"] = "1"
        self._start(ids[0])
        with self.assertRaises(run_registry.RunLimitError):
            self._start(ids[1])
        os.environ["AWDAX_MAX_RUNS"] = "3"
        self._start(ids[1])
        self._start(ids[2])

    def test_invalid_or_zero_env_falls_back_to_defaults(self):
        for bad in ("abc", "0", "-3", "", "1.5"):
            with self.subTest(value=bad):
                self._reset_registry()
                os.environ["AWDAX_MAX_RUNS"] = bad
                os.environ["AWDAX_MAX_RUNS_PER_USER"] = bad
                ids = [self._create_for(f"{bad}-{i}") for i in range(11)]
                for iid in ids[:10]:
                    self._start(iid)  # default global cap 10 (distinct users)
                with self.assertRaises(run_registry.RunLimitError):
                    self._start(ids[10])
                self._reset_registry()
                same = [self._create_for(f"same-{bad}") for _ in range(6)]
                for iid in same[:5]:
                    self._start(iid)  # default per-user cap 5
                with self.assertRaises(run_registry.RunLimitError):
                    self._start(same[5])

    def test_mark_running_and_is_running_keep_working(self):
        run_registry.mark_running("legacy")
        self.assertTrue(run_registry.is_running("legacy"))
        run_registry.mark_stopped("legacy")
        self.assertFalse(run_registry.is_running("legacy"))

    def test_failed_thread_start_releases_slot(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        iid = self._create_for("A")
        with mock.patch.object(orchestrator.threading, "Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("can't start new thread")
            with self.assertRaises(RuntimeError):
                orchestrator.start_run(iid, "g")
        self.assertFalse(run_registry.is_running(iid))
        self._start(self._create_for("B"))


class ResumeAtCapTests(_RegistryBase):
    def test_resume_swallows_limit_error_and_patch_succeeds(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        run_registry.mark_running("someone-else")
        iid = self._create(goal="scrape x")
        with mock.patch.object(orchestrator.threading, "Thread"):
            r = self.client.patch(f"/api/instances/{iid}/live", json={"enabled": True})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(run_registry.is_running(iid))

    def test_resume_instance_does_not_raise_at_cap(self):
        os.environ["AWDAX_MAX_RUNS"] = "1"
        run_registry.mark_running("someone-else")
        iid = self._create(goal="scrape x")
        with mock.patch.object(orchestrator.threading, "Thread"):
            orchestrator.resume_instance(iid, load_instance_session(iid))
        self.assertFalse(run_registry.is_running(iid))


if __name__ == "__main__":
    unittest.main()
