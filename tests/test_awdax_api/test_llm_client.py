import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import llm_client  # noqa: E402

SECRET = "nvapi-SECRET-VALUE"


def _resp(status=200, content="", ):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


class LlmClientTests(unittest.TestCase):
    def setUp(self):
        self._reset()

    def tearDown(self):
        self._reset()

    @staticmethod
    def _reset():
        llm_client._nvidia_key_rejected = False
        llm_client._cooldown_until.clear()
        llm_client._last_good = None

    def test_timed_out_model_is_skipped_until_its_cooldown_ends(self):
        import requests

        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "slow,fast"}
        replies = [requests.Timeout("t"), _resp(200, '{"n": 1}'), _resp(200, '{"n": 2}')]
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("requests.post", side_effect=replies) as post:
            self.assertEqual(llm_client.llm_json("p"), {"n": 1})
            self.assertEqual(llm_client.llm_json("p"), {"n": 2})
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["slow", "fast", "fast"])

    def test_busy_model_cools_down_and_cooled_models_are_a_last_resort(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "a,b", "NVIDIA_COOLDOWN_SECONDS": "300"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("requests.post", side_effect=[_resp(503), _resp(503), _resp(200, '{"ok": 1}')]) as post:
            with self.assertRaises(RuntimeError):
                llm_client.llm_json("p")
            self.assertEqual(llm_client.llm_json("p"), {"ok": 1})
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["a", "b", "a"])

    def test_success_strips_think_and_fences(self):
        content = '<think>hmm {"x": 0}</think>\n```json\n{"a": [1, 2]}\n```'
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": SECRET}, clear=True), \
                mock.patch("requests.post", return_value=_resp(200, content)) as post:
            self.assertEqual(llm_client.llm_json("p"), {"a": [1, 2]})
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], f"Bearer {SECRET}")
        self.assertTrue(post.call_args.args[0].endswith("/chat/completions"))

    def test_json_array_wins_when_first(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": SECRET}, clear=True), \
                mock.patch("requests.post", return_value=_resp(200, 'ok [{"a": 1}]')):
            self.assertEqual(llm_client.llm_json("p"), [{"a": 1}])

    def test_llm_model_tried_first(self):
        env = {"NVIDIA_API_KEY": SECRET, "LLM_MODEL": "my/model"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("requests.post", return_value=_resp(200, "{}")) as post:
            llm_client.llm_json("p")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "my/model")

    def test_500_falls_to_next_model(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "m1,m2"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("requests.post", side_effect=[_resp(500), _resp(200, '{"ok": true}')]) as post:
            self.assertEqual(llm_client.llm_json("p"), {"ok": True})
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["m1", "m2"])

    def test_401_stops_and_hides_key(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "m1,m2"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("requests.post", return_value=_resp(401)) as post:
            with self.assertRaises(RuntimeError) as cm:
                llm_client.llm_json("p")
            self.assertEqual(post.call_count, 1)
            self.assertNotIn(SECRET, str(cm.exception))
            with self.assertRaises(RuntimeError):
                llm_client.llm_text("p")
            self.assertEqual(post.call_count, 1)

    def test_litellm_provider_prefix_is_stripped(self):
        env = {"NVIDIA_API_KEY": "k", "LLM_MODEL": "openai/nvidia/nemotron-x", "NVIDIA_MODELS": "openai/gpt-oss-120b"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm_client._nvidia_models(), ["nvidia/nemotron-x", "openai/gpt-oss-120b"])

    def test_no_keys(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "No LLM key set"):
                llm_client.llm_json("p")

    def test_llm_text_returns_plain_text(self):
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": SECRET}, clear=True), \
                mock.patch("requests.post", return_value=_resp(200, "<think>x</think> hello")):
            self.assertEqual(llm_client.llm_text("p"), "hello")


if __name__ == "__main__":
    unittest.main()
