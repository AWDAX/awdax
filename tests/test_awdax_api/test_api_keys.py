"""Phase 3: per-account API keys, their scopes, and the OpenAPI document that describes the API."""
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402

import api_keys  # noqa: E402
import ui_sessions  # noqa: E402

SECRET = "api-keys-test-secret-api-keys-test-secret-1234567890"


def _session(sub):
    return {"Authorization": "Bearer " + jwt.encode({"sub": sub}, SECRET, algorithm="HS256")}


def _key(key):
    return {"Authorization": f"Bearer {key}"}


class _Base(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        patch.start()
        self.addCleanup(patch.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        env = mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": SECRET}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(self._dir.cleanup)


class StoreTests(_Base):
    def test_a_new_key_works_once_shown_and_is_never_stored_in_clear(self):
        made = api_keys.create_key("alice", "my script", ["read"])
        self.assertTrue(made["key"].startswith("awx_"))
        self.assertGreater(len(made["key"]), 40)
        got = api_keys.resolve_key(made["key"])
        self.assertEqual((got.user_id, got.scopes, got.key_id), ("alice", frozenset({"read"}), made["id"]))
        conn = sqlite3.connect(ui_sessions.DB_PATH)
        dump = " ".join(str(c) for row in conn.execute("SELECT * FROM api_keys") for c in row)
        conn.close()
        self.assertNotIn(made["key"], dump)
        listed = api_keys.list_keys("alice")
        self.assertEqual([k["id"] for k in listed], [made["id"]])
        self.assertNotIn("key", listed[0])
        self.assertNotIn("key_hash", listed[0])
        self.assertTrue(made["key"].startswith(listed[0]["prefix"]))

    def test_unknown_malformed_and_revoked_keys_resolve_to_nothing(self):
        made = api_keys.create_key("alice")
        for bad in ("", "awx_", "awx_" + "x" * 300, "sk_live_123", made["key"] + "x", made["key"][:-1], None, 5):
            self.assertIsNone(api_keys.resolve_key(bad), repr(bad))
        self.assertTrue(api_keys.revoke_key("alice", made["id"]))
        self.assertIsNone(api_keys.resolve_key(made["key"]))
        self.assertFalse(api_keys.revoke_key("alice", made["id"]), "already revoked")
        self.assertEqual(api_keys.list_keys("alice"), [])

    def test_only_the_owner_can_list_or_revoke(self):
        mine = api_keys.create_key("alice")
        self.assertEqual(api_keys.list_keys("bob"), [])
        self.assertFalse(api_keys.revoke_key("bob", mine["id"]))
        self.assertIsNotNone(api_keys.resolve_key(mine["key"]))
        with self.assertRaises(ValueError):
            api_keys.list_keys("")
        with self.assertRaises(ValueError):
            api_keys.create_key("  ")

    def test_scopes_are_checked_and_write_implies_read(self):
        self.assertEqual(api_keys.create_key("a")["scopes"], ["read"])
        self.assertEqual(api_keys.create_key("a", "", ["write"])["scopes"], ["read", "write"])
        for bad in ([], ["admin"], "read", ["read", 5], {"read": True}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                api_keys.create_key("a", "", bad)

    def test_an_account_may_hold_ten_active_keys(self):
        for _ in range(10):
            api_keys.create_key("alice")
        with self.assertRaises(api_keys.KeyLimitError):
            api_keys.create_key("alice")
        api_keys.create_key("bob")  # other accounts are unaffected
        first = api_keys.list_keys("alice")[0]
        api_keys.revoke_key("alice", first["id"])
        api_keys.create_key("alice")  # a revoked key frees a slot

    def test_the_name_is_tidied_and_defaulted(self):
        self.assertEqual(api_keys.create_key("a", "  my   script  ")["name"], "my script")
        self.assertEqual(api_keys.create_key("a", "x" * 200)["name"], "x" * 60)
        self.assertEqual(api_keys.create_key("a", "")["name"], "API key")

    def test_use_is_recorded_but_not_on_every_call(self):
        made = api_keys.create_key("alice")
        api_keys.resolve_key(made["key"])
        first = api_keys.list_keys("alice")[0]["last_used_at"]
        self.assertIsNotNone(first)
        api_keys.resolve_key(made["key"])
        self.assertEqual(api_keys.list_keys("alice")[0]["last_used_at"], first)

    def test_a_pepper_changes_the_hash(self):
        made = api_keys.create_key("alice")
        with mock.patch.dict(os.environ, {"API_KEY_PEPPER": "different"}):
            self.assertIsNone(api_keys.resolve_key(made["key"]))


class HttpTests(_Base):
    def setUp(self):
        super().setUp()
        import app as app_module

        self.client = app_module.app.test_client()

    def _make_key(self, sub="alice", scopes=("read", "write"), name="k"):
        r = self.client.post("/api/keys", json={"name": name, "scopes": list(scopes)}, headers=_session(sub))
        self.assertEqual(r.status_code, 201, r.get_json())
        return r.get_json()

    def test_a_key_acts_as_its_account_and_only_its_account(self):
        alice, bob = self._make_key("alice")["key"], self._make_key("bob")["key"]
        chat = self.client.post("/api/instances", json={"title": "via key"}, headers=_key(alice))
        self.assertEqual(chat.status_code, 201)
        iid = chat.get_json()["id"]
        # the same chat is there for alice's browser session ...
        self.assertEqual([c["id"] for c in self.client.get("/api/instances", headers=_session("alice")).get_json()], [iid])
        # ... and invisible to bob, by key or session
        self.assertEqual(self.client.get("/api/instances", headers=_key(bob)).get_json(), [])
        self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=_key(bob)).status_code, 404)
        self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=_key(alice)).status_code, 200)

    def test_x_api_key_header_works_too(self):
        key = self._make_key()["key"]
        r = self.client.get("/api/me", headers={"X-API-Key": key})
        self.assertEqual((r.status_code, r.get_json()["auth"], r.get_json()["user_id"]), (200, "api_key", "alice"))

    def test_a_read_only_key_can_read_but_not_change_anything(self):
        key = self._make_key(scopes=("read",))["key"]
        iid = self.client.post("/api/instances", json={}, headers=_session("alice")).get_json()["id"]
        self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=_key(key)).status_code, 200)
        for method, path, body in (
            ("post", "/api/instances", {}), ("patch", f"/api/instances/{iid}", {"title": "x"}), ("delete", f"/api/instances/{iid}", None),
            ("post", f"/api/instances/{iid}/messages", {"content": "go"}),
        ):
            r = getattr(self.client, method)(path, json=body, headers=_key(key))
            self.assertEqual(r.status_code, 403, f"{method} {path}")
            self.assertIn("read-only", r.get_json()["detail"])
        self.assertEqual(self.client.get(f"/api/instances/{iid}", headers=_session("alice")).get_json()["title"], "Untitled chat")

    def test_a_read_only_key_may_use_the_posts_that_only_read(self):
        key = self._make_key(scopes=("read",))["key"]
        body = {"question": "x", "columns": [{"index": 0, "key": "a"}], "rows": [{"a": 1}]}
        with mock.patch("ask_data.llm_json", return_value={"kind": "refuse", "reason": "no"}):
            self.assertEqual(self.client.post("/api/ask", json=body, headers=_key(key)).status_code, 200)
        # MCP is JSON-RPC over POST; whether a tool may write is decided by the API call it makes, not here.
        self.assertNotEqual(self.client.post("/api/mcp", json={}, headers=_key(key)).status_code, 403)

    def test_a_key_can_never_manage_keys(self):
        key = self._make_key()["key"]
        kid = self.client.get("/api/keys", headers=_session("alice")).get_json()[0]["id"]
        for method, path in (("get", "/api/keys"), ("post", "/api/keys"), ("delete", f"/api/keys/{kid}")):
            self.assertEqual(getattr(self.client, method)(path, json={}, headers=_key(key)).status_code, 403, f"{method} {path}")
        self.assertEqual(len(self.client.get("/api/keys", headers=_session("alice")).get_json()), 1)

    def test_a_revoked_or_made_up_key_is_a_401(self):
        made = self._make_key()
        self.assertEqual(self.client.get("/api/instances", headers=_key(made["key"])).status_code, 200)
        self.assertEqual(self.client.delete(f"/api/keys/{made['id']}", headers=_session("alice")).status_code, 204)
        for headers in (_key(made["key"]), _key("awx_" + "A" * 43), {"X-API-Key": "awx_nope"}):
            r = self.client.get("/api/instances", headers=headers)
            self.assertEqual(r.status_code, 401)
            self.assertIn("detail", r.get_json())

    def test_keys_are_listed_per_account_and_the_secret_appears_only_at_creation(self):
        made = self._make_key("alice", name="ci")
        self.assertIn("key", made)
        listed = self.client.get("/api/keys", headers=_session("alice")).get_json()
        self.assertEqual([k["name"] for k in listed], ["ci"])
        self.assertNotIn("key", listed[0])
        self.assertEqual(self.client.get("/api/keys", headers=_session("bob")).get_json(), [])
        self.assertEqual(self.client.delete(f"/api/keys/{made['id']}", headers=_session("bob")).status_code, 404)

    def test_bad_key_requests_are_400_and_the_limit_is_409(self):
        self.assertEqual(self.client.post("/api/keys", json={"scopes": ["root"]}, headers=_session("alice")).status_code, 400)
        for _ in range(10):
            self._make_key()
        self.assertEqual(self.client.post("/api/keys", json={}, headers=_session("alice")).status_code, 409)

    def test_a_key_is_rate_limited_on_its_own(self):
        from awdax_api import key_routes

        a, b = self._make_key("alice")["key"], self._make_key("bob")["key"]
        key_routes._recent.clear()
        with mock.patch.object(key_routes, "KEY_REQUESTS_PER_WINDOW", 3):
            codes = [self.client.get("/api/instances", headers=_key(a)).status_code for _ in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
            self.assertEqual(self.client.get("/api/instances", headers=_key(b)).status_code, 200)
            self.assertEqual(self.client.get("/api/instances", headers=_session("alice")).status_code, 200, "a browser session is not limited")
        key_routes._recent.clear()

    def test_public_paths_need_no_credentials_and_the_rest_do(self):
        for path in ("/health", "/ready", "/api/openapi.json"):
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in ("/api/instances", "/api/me", "/api/keys"):
            self.assertEqual(self.client.get(path).status_code, 401, path)


class DevModeKeyTests(_Base):
    """npm run dev:agent runs the backend in dev mode (no sign-in): keys must work there too."""

    def test_keys_work_in_dev_mode_and_stay_scoped(self):
        import app as app_module

        client = app_module.app.test_client()
        with mock.patch.dict(os.environ, {"AWDAX_AUTH_MODE": "dev"}):
            made = client.post("/api/keys", json={"name": "dev", "scopes": ["read"]}).get_json()
            me = client.get("/api/me", headers=_key(made["key"]))
            self.assertEqual((me.status_code, me.get_json()["auth"]), (200, "api_key"))
            self.assertEqual(client.post("/api/instances", json={}, headers=_key(made["key"])).status_code, 403, "still read-only")
            self.assertEqual(client.get("/api/instances", headers=_key("awx_" + "q" * 43)).status_code, 401, "an unknown key is not the dev user")
            self.assertEqual(client.get("/api/keys", headers=_key(made["key"])).status_code, 403)


class OpenApiTests(_Base):
    def setUp(self):
        super().setUp()
        import app as app_module

        self.app = app_module.app
        self.spec = self.app.test_client().get("/api/openapi.json").get_json()

    def _routes(self):
        found = set()
        for rule in self.app.url_map.iter_rules():
            if not rule.endpoint.startswith("awdax_api."):
                continue
            path = re.sub(r"<(?:[a-z]+:)?([a-z_]+)>", r"{\1}", rule.rule)
            for method in rule.methods - {"HEAD", "OPTIONS"}:
                found.add((method.lower(), path))
        return found

    def _documented(self):
        return {(m, p) for p, ops in self.spec["paths"].items() for m in ops}

    def test_every_route_is_documented_and_nothing_else(self):
        self.assertEqual(self._routes() - self._documented(), set(), "routes missing from awdax_api/openapi.py")
        self.assertEqual(self._documented() - self._routes(), set(), "documented routes that do not exist")

    def test_it_is_a_complete_openapi_document(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        self.assertIn("apiKey", self.spec["components"]["securitySchemes"])
        text = str(self.spec)
        for ref in re.findall(r"#/components/schemas/(\w+)", text):
            self.assertIn(ref, self.spec["components"]["schemas"], ref)
        for path, ops in self.spec["paths"].items():
            for method, op in ops.items():
                self.assertTrue(op.get("summary"), (method, path))
                self.assertTrue(op.get("responses"), (method, path))
                declared = set(re.findall(r"{(\w+)}", path))
                given = {p["name"] for p in op.get("parameters", []) if p["in"] == "path"}
                self.assertEqual(declared, given, (method, path))

    def test_public_calls_are_marked_as_needing_no_key(self):
        for path in ("/health", "/ready", "/api/openapi.json"):
            self.assertEqual(self.spec["paths"][path]["get"]["security"], [])


if __name__ == "__main__":
    unittest.main()
