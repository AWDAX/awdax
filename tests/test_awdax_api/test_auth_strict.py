"""BE-01 / BE-03: with PROXY_SHARED_SECRET set, identity is only ever proven; never forged or 'anonymous'."""
import logging
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt  # noqa: E402

import auth_helper  # noqa: E402
from auth_helper import AuthError, get_user_id  # noqa: E402

PROXY = "proxy-secret-value"
JWT_SECRET = "real-secret-real-secret-real-secret-1"


def _req(headers=None, cookie=None):
    req = mock.Mock()
    req.headers = dict(headers or {})
    req.cookies = {"awdax_token": cookie} if cookie else {}
    return req


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _forged(sub="victim"):
    return jwt.encode({"sub": sub}, "attacker-key-attacker-key-attacker-key", algorithm="HS256")


class _Base(unittest.TestCase):
    def setUp(self):
        auth_helper._warned_unverified = False


class StrictModeTests(_Base):
    def _env(self, **extra):
        return mock.patch.dict(os.environ, {"PROXY_SHARED_SECRET": PROXY, **extra}, clear=True)

    def test_forged_unsigned_jwt_is_rejected(self):
        unsigned = jwt.encode({"sub": "victim"}, key=None, algorithm="none")
        with self._env():
            for token in (unsigned, _forged()):
                with self.assertRaises(AuthError):
                    get_user_id(_req(_bearer(token)))
                with self.assertRaises(AuthError):
                    get_user_id(_req(cookie=token))

    def test_forged_jwt_is_rejected_even_when_a_jwt_secret_is_set(self):
        with self._env(SUPABASE_JWT_SECRET=JWT_SECRET):
            with self.assertRaises(AuthError):
                get_user_id(_req(_bearer(_forged())))

    def test_no_identity_is_rejected_not_anonymous(self):
        with self._env():
            with self.assertRaises(AuthError):
                get_user_id(_req())

    def test_user_header_with_correct_secret_is_that_user(self):
        with self._env():
            self.assertEqual(get_user_id(_req({"X-User-Id": " alice ", "X-Proxy-Secret": PROXY})), "alice")

    def test_user_header_with_correct_secret_wins_over_unverifiable_es256_style_token(self):
        # The proxy forwards the original (ES256) token too; the backend cannot verify it and must not need to.
        with self._env():
            headers = {"X-User-Id": "alice", "X-Proxy-Secret": PROXY, **_bearer("header.payload.sig")}
            self.assertEqual(get_user_id(_req(headers)), "alice")

    def test_user_header_with_wrong_or_missing_secret_is_rejected(self):
        with self._env():
            for headers in ({"X-User-Id": "alice", "X-Proxy-Secret": "bad"}, {"X-User-Id": "alice"}):
                with self.assertRaises(AuthError):
                    get_user_id(_req(headers))

    def test_wrong_secret_is_not_downgraded_to_a_valid_token(self):
        tok = jwt.encode({"sub": "bob"}, JWT_SECRET, algorithm="HS256")
        with self._env(SUPABASE_JWT_SECRET=JWT_SECRET):
            with self.assertRaises(AuthError):
                get_user_id(_req({"X-User-Id": "alice", "X-Proxy-Secret": "bad", **_bearer(tok)}))

    def test_token_signed_with_jwt_secret_is_that_user(self):
        for alg in ("HS256", "HS384", "HS512"):
            tok = jwt.encode({"sub": "carol"}, JWT_SECRET, algorithm=alg)
            with self._env(SUPABASE_JWT_SECRET=JWT_SECRET):
                self.assertEqual(get_user_id(_req(_bearer(tok))), "carol", alg)
                self.assertEqual(get_user_id(_req(cookie=tok)), "carol", alg)

    def test_token_with_wrong_signature_is_rejected(self):
        tok = jwt.encode({"sub": "carol"}, "other-secret-other-secret-other-secret", algorithm="HS256")
        with self._env(SUPABASE_JWT_SECRET=JWT_SECRET):
            with self.assertRaises(AuthError):
                get_user_id(_req(_bearer(tok)))

    def test_valid_token_without_sub_is_rejected(self):
        tok = jwt.encode({"email": "x@y.z"}, JWT_SECRET, algorithm="HS256")
        with self._env(SUPABASE_JWT_SECRET=JWT_SECRET):
            with self.assertRaises(AuthError):
                get_user_id(_req(_bearer(tok)))

    def test_strict_mode_does_not_warn(self):
        with self._env(), self.assertNoLogs(level=logging.WARNING):
            get_user_id(_req({"X-User-Id": "alice", "X-Proxy-Secret": PROXY}))


class PermissiveModeTests(_Base):
    def _env(self, **extra):
        return mock.patch.dict(os.environ, dict(extra), clear=True)

    def test_bare_user_header_works(self):
        with self._env():
            self.assertEqual(get_user_id(_req({"X-User-Id": "dev"})), "dev")

    def test_no_identity_is_anonymous(self):
        with self._env():
            self.assertEqual(get_user_id(_req()), "anonymous")

    def test_unverified_token_still_decodes(self):
        with self._env():
            self.assertEqual(get_user_id(_req(_bearer(_forged("someone")))), "someone")

    def test_garbage_token_is_still_rejected(self):
        with self._env():
            with self.assertRaises(AuthError):
                get_user_id(_req(_bearer("not-a-jwt")))

    def test_warning_is_logged_once_per_process(self):
        with self._env():
            with self.assertLogs(level=logging.WARNING) as logs:
                get_user_id(_req())
                get_user_id(_req({"X-User-Id": "dev"}))
                get_user_id(_req())
            hits = [m for m in logs.output if "PROXY_SHARED_SECRET" in m]
            self.assertEqual(len(hits), 1, logs.output)
            self.assertIn("unverified", hits[0].lower())


class StrictModeOverHttpTests(_Base):
    def setUp(self):
        super().setUp()
        import tempfile

        import ui_sessions

        self._dir = tempfile.TemporaryDirectory()
        patch = mock.patch.object(ui_sessions, "DB_PATH", Path(self._dir.name) / "t.sqlite")
        patch.start()
        self.addCleanup(patch.stop)
        ui_sessions._initialized = None
        self.addCleanup(setattr, ui_sessions, "_initialized", None)
        self.addCleanup(lambda: self._dir.cleanup())
        import app as app_module

        self.client = app_module.app.test_client()

    def test_forged_jwt_and_anonymous_get_json_401(self):
        with mock.patch.dict(os.environ, {"PROXY_SHARED_SECRET": PROXY}, clear=True):
            r = self.client.get("/api/instances", headers=_bearer(_forged()))
            self.assertEqual(r.status_code, 401)
            self.assertIn("detail", r.get_json())
            self.assertEqual(self.client.get("/api/instances").status_code, 401)
            self.assertEqual(self.client.post("/api/instances", json={}).status_code, 401)

    def test_proxy_headers_work_and_wrong_secret_is_401(self):
        with mock.patch.dict(os.environ, {"PROXY_SHARED_SECRET": PROXY}, clear=True):
            ok = self.client.post("/api/instances", json={}, headers={"X-User-Id": "A", "X-Proxy-Secret": PROXY})
            self.assertEqual(ok.status_code, 201)
            bad = self.client.post("/api/instances", json={}, headers={"X-User-Id": "A", "X-Proxy-Secret": "bad"})
            self.assertEqual(bad.status_code, 401)

    def test_health_needs_no_identity_in_strict_mode(self):
        with mock.patch.dict(os.environ, {"PROXY_SHARED_SECRET": PROXY}, clear=True):
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/ready").status_code, 200)


if __name__ == "__main__":
    unittest.main()
