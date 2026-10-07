"""Hardening: ws keepalive, background writers keep user edits, prompt/title limits, light list endpoint."""
import queue
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from awdax_api import orchestrator, routes, serializers  # noqa: E402
from awdax_api.session_store import load_instance_session  # noqa: E402
from test_run_lifecycle import _Base  # noqa: E402

live_bridge_module = sys.modules["awdax_api.live_bridge"]


class _ClosedSocket(Exception):
    pass


class PumpTests(unittest.TestCase):
    def test_idle_subscriber_gets_ping_and_exits_when_socket_is_closed(self):
        class Sub:
            calls = 0

            def get(self, timeout=None):
                Sub.calls += 1
                assert timeout == 0.01
                raise queue.Empty

        sent = []

        def send(data):
            sent.append(data)
            if len(sent) == 2:
                raise _ClosedSocket

        with self.assertRaises(_ClosedSocket):
            routes._pump(Sub(), send, timeout=0.01)
        self.assertEqual(sent, ['{"type": "ping"}', '{"type": "ping"}'])

    def test_messages_are_forwarded(self):
        q: queue.Queue = queue.Queue()
        q.put({"type": "status"})
        sent = []

        def send(data):
            sent.append(data)
            if len(sent) == 2:
                raise _ClosedSocket

        with self.assertRaises(_ClosedSocket):
            routes._pump(q, send, timeout=0.01)
        self.assertEqual(sent, ['{"type": "status"}', '{"type": "ping"}'])


class UserEditsSurviveBackgroundWritesTests(_Base):
    def test_background_writers_do_not_revert_rename_or_pause(self):
        iid = self._create(title="Old", keep_live=True)
        stale = load_instance_session(iid)
        self.assertEqual(self.client.patch(f"/api/instances/{iid}", json={"title": "New", "archived": True}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/instances/{iid}/live", json={"enabled": False}).status_code, 200)

        with mock.patch.object(orchestrator, "load_instance_session", return_value=stale), mock.patch.object(
            orchestrator.live_bridge, "notify_instance"
        ):
            orchestrator._on_progress(iid, "extracting", "x")
            orchestrator._on_source(iid, {"url": "http://a"})
            orchestrator._on_job(iid, "job1")
        orchestrator.unregister_job(iid, "job1")

        got = self.client.get(f"/api/instances/{iid}").get_json()
        self.assertEqual(got["title"], "New")
        self.assertTrue(got["archived"])
        self.assertFalse(got["live_enabled"])
        self.assertFalse(self.client.get(f"/api/instances/{iid}/live").get_json()["enabled"])
        # The background write itself still landed.
        self.assertEqual(load_instance_session(iid)["awdax_run"]["phase"], "extracting")

    def test_live_bridge_writer_keeps_user_fields(self):
        iid = self._create(title="Old", keep_live=True)
        stale = load_instance_session(iid)
        self.client.patch(f"/api/instances/{iid}", json={"title": "New"})
        self.client.patch(f"/api/instances/{iid}/live", json={"enabled": False})
        bridge = live_bridge_module.LiveBridge()
        with mock.patch.object(live_bridge_module, "load_instance_session", return_value=stale), mock.patch.object(
            bridge, "_resolve_instance", return_value=iid
        ):
            bridge._handle_backend_event({"type": "log", "message": "hi"}, "universal")
        got = self.client.get(f"/api/instances/{iid}").get_json()
        self.assertEqual((got["title"], got["live_enabled"]), ("New", False))


class PromptAndTitleLimitTests(_Base):
    def test_message_over_2000_is_rejected(self):
        iid = self._create()
        with mock.patch.object(routes, "submit_run") as sr:
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "a" * 2001})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["detail"], "Request is too long (2000 characters max)")
        sr.assert_not_called()

    def test_message_of_2000_is_accepted(self):
        iid = self._create()
        with mock.patch.object(routes, "submit_run") as sr:
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "a" * 2000})
        self.assertEqual(r.status_code, 201)
        sr.assert_called_once()

    def test_goal_over_2000_is_rejected_on_create(self):
        r = self.client.post("/api/instances", json={"title": "t", "goal": "g" * 2001})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post("/api/instances", json={"title": "t", "goal": "g" * 2000}).status_code, 201)

    def test_long_title_is_cut_to_80(self):
        iid = self._create()
        r = self.client.patch(f"/api/instances/{iid}", json={"title": "x" * 200})
        self.assertEqual(r.get_json()["title"], "x" * 80)
        self.assertEqual(load_instance_session(iid)["title"], "x" * 80)

    def test_blank_title_keeps_the_old_one(self):
        iid = self._create(title="Keep me")
        r = self.client.patch(f"/api/instances/{iid}", json={"title": "   "})
        self.assertEqual(r.get_json()["title"], "Keep me")


class ListEndpointTests(_Base):
    def test_list_skips_row_count_but_detail_has_it(self):
        iid = self._create()
        with mock.patch.object(serializers, "dataset_row_count", return_value=7) as rc:
            rows = self.client.get("/api/instances").get_json()
            rc.assert_not_called()
            self.assertEqual([r["id"] for r in rows], [iid])
            self.assertNotIn("dataset_row_count", rows[0])
            detail = self.client.get(f"/api/instances/{iid}").get_json()
        self.assertEqual(detail["dataset_row_count"], 7)


if __name__ == "__main__":
    unittest.main()
