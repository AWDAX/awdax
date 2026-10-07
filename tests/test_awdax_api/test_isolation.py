"""Phase 1: one user can never see, change or hear another user's chats (strict auth, the default)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402

import ui_sessions  # noqa: E402

SECRET = "isolation-test-secret-isolation-test-secret-1234567890"
PROXY = "proxy-secret-value"

CHAT_ROUTES = [
    ("get", ""), ("patch", ""), ("delete", ""), ("get", "/messages"), ("post", "/messages"),
    ("get", "/dataset"), ("delete", "/dataset"), ("get", "/dashboard"), ("get", "/live"), ("patch", "/live"),
    ("get", "/live/stream"), ("get", "/sources"), ("get", "/failed-links"), ("get", "/dataset/stats"), ("post", "/dataset/rescore"),
    ("get", "/graph/parameters"), ("get", "/graph"),
]


def _token(sub):
    return jwt.encode({"sub": sub}, SECRET, algorithm="HS256")


def _as(sub):
    return {"Authorization": f"Bearer {_token(sub)}"}


class _Base(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        patch.start()
        self.addCleanup(patch.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        env = mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": SECRET, "PROXY_SHARED_SECRET": PROXY}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        import app as app_module

        self.client = app_module.app.test_client()
        self.addCleanup(lambda: self._dir.cleanup())


class TwoUsersTests(_Base):
    def _chat_for(self, sub):
        r = self.client.post("/api/instances", json={"title": f"{sub}'s chat"}, headers=_as(sub))
        self.assertEqual(r.status_code, 201)
        return r.get_json()["id"]

    def test_user_b_gets_404_on_every_chat_route_of_user_a(self):
        iid = self._chat_for("user-a")
        for method, path in CHAT_ROUTES:
            resp = getattr(self.client, method)(f"/api/instances/{iid}{path}", json={"content": "hi"}, headers=_as("user-b"))
            self.assertEqual(resp.status_code, 404, f"{method} {path}")
        listed = self.client.get("/api/instances", headers=_as("user-a")).get_json()
        self.assertEqual([x["id"] for x in listed], [iid])
        self.assertEqual(self.client.get("/api/instances", headers=_as("user-b")).get_json(), [])
        # B's delete changed nothing.
        self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=_as("user-a")).status_code, 200)

    def test_each_user_lists_only_their_own_chats(self):
        a1, a2, b1 = self._chat_for("user-a"), self._chat_for("user-a"), self._chat_for("user-b")

        def ids(who):
            return {x["id"] for x in self.client.get("/api/instances", headers=_as(who)).get_json()}

        self.assertEqual(ids("user-a"), {a1, a2})
        self.assertEqual(ids("user-b"), {b1})

    def test_no_identity_is_401_on_every_route(self):
        iid = self._chat_for("user-a")
        self.assertEqual(self.client.get("/api/instances").status_code, 401)
        self.assertEqual(self.client.post("/api/instances", json={}).status_code, 401)
        self.assertEqual(self.client.post("/api/ask", json={"columns": [], "rows": []}).status_code, 401)
        for method, path in CHAT_ROUTES:
            resp = getattr(self.client, method)(f"/api/instances/{iid}{path}", json={"content": "hi"})
            self.assertEqual(resp.status_code, 401, f"{method} {path}")

    def test_a_user_id_header_without_the_proxy_secret_is_401_never_that_user(self):
        iid = self._chat_for("user-a")
        for headers in ({"X-User-Id": "user-a"}, {"X-User-Id": "user-a", "X-Proxy-Secret": "wrong"}):
            self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=headers).status_code, 401)
            self.assertEqual(self.client.get("/api/instances", headers=headers).status_code, 401)

    def test_a_blank_user_id_is_401_not_every_users_chats(self):
        self._chat_for("user-a")
        for blank in ("", " ", "   "):
            r = self.client.get("/api/instances", headers={"X-User-Id": blank, "X-Proxy-Secret": PROXY})
            self.assertEqual(r.status_code, 401, repr(blank))

    def test_ask_works_for_a_signed_in_user(self):
        body = {"question": "x", "columns": [{"index": 0, "key": "a"}], "rows": [{"a": 1}]}
        with mock.patch("ask_data.llm_json", return_value={"kind": "refuse", "reason": "no"}):
            self.assertEqual(self.client.post("/api/ask", json=body, headers=_as("user-a")).status_code, 200)

    def test_bad_max_pages_is_400_before_anything_happens(self):
        iid = self._chat_for("user-a")
        for bad in ("lots", [1], {"n": 1}, float("inf")):
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "go", "max_pages": bad}, headers=_as("user-a"))
            self.assertEqual(r.status_code, 400, repr(bad))
        self.assertEqual(self.client.get(f"/api/instances/{iid}/messages", headers=_as("user-a")).get_json(), [])

    def test_max_pages_is_clamped(self):
        iid = self._chat_for("user-a")
        with mock.patch("awdax_api.routes.submit_run") as start:
            r = self.client.post(f"/api/instances/{iid}/messages", json={"content": "go", "max_pages": 9999}, headers=_as("user-a"))
        self.assertEqual(r.status_code, 201)
        start.assert_called_once_with(iid, "go", max_pages=10)


class StorageFailsClosedTests(_Base):
    def test_an_empty_user_id_is_an_error_not_everyone(self):
        ui_sessions.create_session(user_id="u1", title="one")
        for blank in ("", "  ", None):
            with self.assertRaises(ValueError):
                ui_sessions.list_sessions(blank)
            with self.assertRaises(ValueError):
                ui_sessions.get_session("x", blank)
            with self.assertRaises(ValueError):
                ui_sessions.delete_session("x", blank)

    def test_a_stale_copy_cannot_take_over_someone_elses_chat(self):
        mine = ui_sessions.create_session(user_id="owner", title="mine")
        hostile = dict(mine, user_id="intruder", title="hijacked")
        with self.assertRaises(PermissionError):
            ui_sessions.save_session(hostile, allow_insert=False)
        kept = ui_sessions.get_session(mine["id"], "owner")
        self.assertEqual((kept["user_id"], kept["title"]), ("owner", "mine"))
        self.assertIsNone(ui_sessions.get_session(mine["id"], "intruder"))

    def test_delete_is_scoped_to_the_owner(self):
        mine = ui_sessions.create_session(user_id="owner", title="mine")
        self.assertFalse(ui_sessions.delete_session(mine["id"], "intruder"))
        self.assertTrue(ui_sessions.delete_session(mine["id"], "owner"))


class SessionsAdminTests(_Base):
    def setUp(self):
        super().setUp()
        sys.path.insert(0, str(ROOT / "scripts"))
        self.addCleanup(sys.path.remove, str(ROOT / "scripts"))
        import sessions_admin

        self.admin = sessions_admin

    def test_assign_hands_an_unowned_chat_to_an_account_and_never_steals_an_owned_one(self):
        orphan = ui_sessions.create_session(title="old shared chat")  # stored under "anonymous"
        owned = ui_sessions.create_session(user_id="alice", title="alice's")
        self.assertEqual(self.admin.assign(orphan["id"], "bob"), 0)
        self.assertIsNotNone(ui_sessions.get_session(orphan["id"], "bob"))
        self.assertEqual(self.admin.assign(owned["id"], "bob"), 1)
        self.assertIsNone(ui_sessions.get_session(owned["id"], "bob"))
        self.assertEqual(self.admin.assign(orphan["id"], "anonymous"), 2)

    def test_purge_needs_confirmation_and_only_removes_unowned_chats(self):
        ui_sessions.create_session(title="old shared chat")
        keep = ui_sessions.create_session(user_id="alice", title="alice's")
        self.assertEqual(self.admin.purge_anonymous(False), 2)
        self.assertEqual(self.admin.purge_anonymous(True), 0)
        self.assertEqual([s["id"] for s in ui_sessions.list_all_sessions_internal()], [keep["id"]])


class LiveEventRoutingTests(unittest.TestCase):
    def setUp(self):
        from awdax_api import run_registry
        from awdax_api.live_bridge import LiveBridge

        self.bridge = LiveBridge()
        self.registry = run_registry
        run_registry.mark_running("chat-of-user-b")
        self.addCleanup(run_registry.mark_stopped, "chat-of-user-b")

    def test_an_event_goes_to_the_chat_named_on_it(self):
        self.assertEqual(self.bridge._resolve_instance({"instance_id": "chat-of-user-a"}, "regulatory"), "chat-of-user-a")

    def test_a_job_event_goes_to_the_chat_that_owns_the_job(self):
        self.registry.register_job("chat-of-user-a", "job-1")
        self.addCleanup(self.registry.unregister_job, "chat-of-user-a", "job-1")
        self.assertEqual(self.bridge._resolve_instance({"job_id": "job-1"}, "universal"), "chat-of-user-a")

    def test_an_unaddressed_event_is_dropped_not_given_to_whichever_chat_is_running(self):
        # user B's chat is running; an eGazette event naming nobody must not land in it.
        self.assertIsNone(self.bridge._resolve_instance({"type": "log", "message": "row"}, "regulatory"))
        self.assertIsNone(self.bridge._resolve_instance({"job_id": "unknown-job"}, "universal"))


class RegulatoryOwnerTagTests(unittest.TestCase):
    def test_events_of_a_scrape_carry_the_chat_that_started_it(self):
        from RegulatoryFeed import RegulatoryFeedService

        # A separate instance: the shared one feeds the live bridge's background thread.
        service = RegulatoryFeedService()
        sub = service.subscribe_events()
        service._owner_instance = "chat-1"
        service.emit_event("log", {"message": "hello"})
        self.assertEqual(sub.get_nowait()["instance_id"], "chat-1")
        service._owner_instance = None
        service.emit_event("log", {"message": "later"})
        self.assertNotIn("instance_id", sub.get_nowait())


if __name__ == "__main__":
    unittest.main()
