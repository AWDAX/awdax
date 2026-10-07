"""The pre-React API and its page were removed from app.py (3 Oct 2026). Callers must see exactly what the old
legacy guard gave them: the API's JSON 404 on every retired path and method, while the React API still answers."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app  # noqa: E402

RETIRED = [
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
    ("get", "/index.html"),
    ("get", "/api/instancesfoo"),
]


class RetiredRoutesTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {"AWDAX_AUTH_MODE": "dev"})
        env.start()
        self.addCleanup(env.stop)
        self.client = app.test_client()

    def test_every_retired_path_is_the_json_404(self):
        for method, path in RETIRED:
            with self.subTest(method=method, path=path):
                r = getattr(self.client, method)(path)
                self.assertEqual(r.status_code, 404)
                self.assertEqual(r.get_json(), {"detail": "Not found"})

    def test_the_react_api_still_answers(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/ready").status_code, 200)
        self.assertEqual(self.client.get("/api/instances").status_code, 200)

    def test_an_unknown_instance_is_still_the_api_404(self):
        r = self.client.get("/api/instances/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertIn("detail", r.get_json())


if __name__ == "__main__":
    unittest.main()
