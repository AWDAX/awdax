"""Per-user budgets for chats and runs, max_pages and limit clamps, and caps on open live streams."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from awdax_api import routes  # noqa: E402
from awdax_api.budget import Budget  # noqa: E402
from awdax_api.live_bridge import LiveBridge, MAX_STREAMS_PER_CHAT, MAX_STREAMS_PER_USER  # noqa: E402
from awdax_api.session_store import load_instance_session  # noqa: E402
from test_run_lifecycle import _Base  # noqa: E402

A = {"X-User-Id": "A"}


class BudgetTests(unittest.TestCase):
    def test_spend_until_empty_then_refill_after_the_window(self):
        b = Budget(2, 60)
        with mock.patch("awdax_api.budget.time.monotonic", return_value=100.0):
            self.assertEqual([b.spend("u"), b.spend("u"), b.spend("u")], [True, True, False])
            self.assertTrue(b.spend("other"), "budgets are per user")
        with mock.patch("awdax_api.budget.time.monotonic", return_value=161.0):
            self.assertTrue(b.spend("u"))


class RouteLimitTests(_Base):
    def _chat(self):
        return self.client.post("/api/instances", json={}, headers=A).get_json()["id"]

    def test_new_chats_have_a_per_user_budget(self):
        with mock.patch.object(routes, "CHAT_BUDGET", Budget(1, 3600)):
            self.assertEqual(self.client.post("/api/instances", json={}, headers=A).status_code, 201)
            refused = self.client.post("/api/instances", json={}, headers=A)
        self.assertEqual(refused.status_code, 429)

    def test_runs_have_a_per_user_budget_and_a_refusal_changes_nothing(self):
        iid = self._chat()
        with mock.patch.object(routes, "RUN_BUDGET", Budget(0, 3600)), mock.patch.object(routes, "submit_run") as start:
            res = self.client.post(f"/api/instances/{iid}/messages", json={"content": "cars"}, headers=A)
        self.assertEqual(res.status_code, 429)
        start.assert_not_called()
        self.assertEqual(load_instance_session(iid)["messages"], [])

    def test_max_pages_is_clamped_and_garbage_is_400_before_any_side_effect(self):
        iid = self._chat()
        with mock.patch.object(routes, "submit_run") as start:
            self.client.post(f"/api/instances/{iid}/messages", json={"content": "cars", "max_pages": 100000}, headers=A)
            self.assertEqual(start.call_args.kwargs["max_pages"], routes.MAX_PAGES_LIMIT)
        iid2 = self._chat()
        with mock.patch.object(routes, "submit_run") as start:
            bad = self.client.post(f"/api/instances/{iid2}/messages", json={"content": "cars", "max_pages": "abc"}, headers=A)
        self.assertEqual(bad.status_code, 400)
        start.assert_not_called()
        self.assertEqual(load_instance_session(iid2)["messages"], [])

    def test_a_negative_dataset_limit_is_not_unlimited(self):
        iid = self._chat()
        with mock.patch.object(routes, "build_dataset_table", return_value=None) as build:
            self.client.get(f"/api/instances/{iid}/dataset?limit=-1", headers=A)
        self.assertEqual(build.call_args.kwargs["limit"], 1)

    def test_too_many_open_streams_is_429(self):
        iid = self._chat()
        with mock.patch("awdax_api.live_routes.live_bridge.subscribe", return_value=None):
            self.assertEqual(self.client.get(f"/api/instances/{iid}/live/stream", headers=A).status_code, 429)


class StreamCapTests(unittest.TestCase):
    def test_caps_per_chat_and_per_user_and_release_on_unsubscribe(self):
        bridge = LiveBridge()
        per_chat = [bridge.subscribe("c1", owner="u") for _ in range(MAX_STREAMS_PER_CHAT)]
        self.assertTrue(all(per_chat))
        self.assertIsNone(bridge.subscribe("c1", owner="u"), "chat full")
        others = [bridge.subscribe(f"c{i}", owner="u") for i in range(2, 2 + MAX_STREAMS_PER_USER - MAX_STREAMS_PER_CHAT)]
        self.assertTrue(all(others))
        self.assertIsNone(bridge.subscribe("c99", owner="u"), "user full")
        self.assertIsNotNone(bridge.subscribe("c99", owner="someone-else"))
        bridge.unsubscribe("c1", per_chat[0])
        bridge.unsubscribe("c1", per_chat[0])  # twice is harmless (stream end + response close)
        self.assertIsNotNone(bridge.subscribe("c99", owner="u"), "one slot freed, exactly one")
        self.assertIsNone(bridge.subscribe("c98", owner="u"))
        self.assertIsNotNone(bridge.subscribe("c1", owner=None), "internal subscribers are never capped")


if __name__ == "__main__":
    unittest.main()
