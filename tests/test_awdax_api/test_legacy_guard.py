"""BE-02: the old (pre-React) API in app.py must not be reachable unless AWDAX_LEGACY_API is on."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, jsonify  # noqa: E402

LEGACY = [
    ("get", "/"),
    ("get", "/api/sessions"),
    ("post", "/api/sessions"),
    ("get", "/api/sessions/abc"),
    ("patch", "/api/sessions/abc"),
    ("delete", "/api/sessions/abc"),
    ("get", "/api/feed"),
    ("get", "/api/scrape/status"),
    ("get", "/api/events"),
    ("post", "/api/scrape/live/stop"),
    ("post", "/api/scrape/start"),
    ("post", "/api/prompt"),
    ("post", "/api/queries"),
    ("post", "/api/table-headers"),
    ("post", "/api/discover"),
    ("post", "/api/inspect"),
    ("post", "/api/scrape/run"),
]


def _dummy_app():
    from awdax_api import legacy_guard

    app = Flask(__name__)
    legacy_guard.install(app)
    methods = ["GET", "POST", "PATCH", "DELETE"]
    for path in ["/", "/health", "/ready", "/api/instances", "/api/instances/<iid>", "/api/instances/<iid>/live/ws",
                 "/api/instances/<iid>/live/stream", "/api/sessions", "/api/sessions/<sid>", "/api/feed",
                 "/api/events", "/api/scrape/live/stop", "/api/instancesfoo"]:
        app.add_url_rule(path, endpoint=path, view_func=lambda **kw: jsonify({"ok": True}), methods=methods)
    return app


class LegacyGuardUnitTests(unittest.TestCase):
    def setUp(self):
        self.client = _dummy_app().test_client()

    def test_legacy_paths_are_404_by_default_for_every_method(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for method, path in LEGACY:
                r = getattr(self.client, method)(path)
                self.assertEqual(r.status_code, 404, f"{method} {path}")
                self.assertIn("detail", r.get_json())

    def test_unknown_non_allowed_path_is_json_404_too(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            r = self.client.get("/nope")
            self.assertEqual(r.status_code, 404)
            self.assertIn("detail", r.get_json())

    def test_allowed_paths_pass(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for path in ["/health", "/ready", "/api/instances", "/api/instances/x", "/api/instances/x/live/stream"]:
                self.assertEqual(self.client.get(path).status_code, 200, path)
            for method in ("post", "patch", "delete"):
                self.assertEqual(getattr(self.client, method)("/api/instances/x").status_code, 200, method)

    def test_websocket_style_path_passes(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            # The guard looks at the path only, so the handshake headers don't matter here.
            r = self.client.get("/api/instances/x/live/ws")
            self.assertEqual(r.status_code, 200)

    def test_prefix_lookalike_is_not_allowed(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.client.get("/api/instancesfoo").status_code, 404)

    def test_flag_reenables_legacy_paths(self):
        for value in ("1", "true", "TRUE"):
            with mock.patch.dict(os.environ, {"AWDAX_LEGACY_API": value}, clear=True):
                for method, path in LEGACY[:3] + LEGACY[6:7]:
                    r = getattr(self.client, method)(path)
                    self.assertNotEqual(r.status_code, 404, f"{value} {method} {path}")

    def test_other_flag_values_keep_legacy_off(self):
        for value in ("", "0", "false", "no"):
            with mock.patch.dict(os.environ, {"AWDAX_LEGACY_API": value}, clear=True):
                self.assertEqual(self.client.get("/api/sessions").status_code, 404, value)

    def test_options_preflight_is_not_touched(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            plain = Flask(__name__)
            plain.add_url_rule("/api/sessions", "s", lambda: "x", methods=["GET"])
            expected = plain.test_client().options("/api/sessions").status_code
            self.assertEqual(self.client.options("/api/sessions").status_code, expected)
            self.assertEqual(self.client.options("/api/instances").status_code, 200)


class LegacyGuardRealAppTests(unittest.TestCase):
    def setUp(self):
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

    def test_real_app_hides_legacy_routes_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for method, path in LEGACY:
                r = getattr(self.client, method)(path, json={}) if method != "get" else self.client.get(path)
                self.assertEqual(r.status_code, 404, f"{method} {path}")
                self.assertIn("detail", r.get_json(), f"{method} {path}")

    def test_real_app_keeps_react_routes_and_health(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.client.get("/health").status_code, 200)
            self.assertEqual(self.client.get("/ready").status_code, 200)
            self.assertEqual(self.client.get("/api/instances/does-not-exist").status_code, 404)

    def test_real_app_flag_restores_legacy(self):
        with mock.patch.dict(os.environ, {"AWDAX_LEGACY_API": "1"}, clear=True):
            r = self.client.get("/api/sessions")
            self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
