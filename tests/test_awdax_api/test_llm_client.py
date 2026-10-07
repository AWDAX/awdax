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
        llm_client._timed_out.clear()
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

    def test_a_budget_caps_each_wait_and_stops_trying_models_when_spent(self):
        import requests

        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "a,b,c", "NVIDIA_TIMEOUT_SECONDS": "90"}
        clock = [1000.0]

        def slow(*_a, **kw):
            clock[0] += kw["timeout"]  # each model uses its whole wait
            raise requests.Timeout("t")

        with mock.patch.dict(os.environ, env, clear=True), mock.patch("llm_client.time.monotonic", lambda: clock[0]), \
                mock.patch("requests.post", side_effect=slow) as post, self.assertRaises(RuntimeError):
            llm_client.llm_json("p", budget_s=60)
        # One model, waited the 60 s budget rather than 90; the rest were never tried.
        self.assertEqual([c.kwargs["timeout"] for c in post.call_args_list], [60])

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


class FakeGemini:
    """Stands in for google.generativeai: records each model built and each call; `answers` is consumed one per call."""

    def __init__(self, answers):
        self.answers, self.built, self.calls = list(answers), [], []

    def configure(self, api_key):
        pass

    def GenerativeModel(self, name, generation_config=None):  # noqa: N802 - the real name
        self.built.append((name, generation_config))
        outer = self

        class Model:
            def generate_content(self, prompt, request_options=None):
                outer.calls.append((name, request_options))
                answer = outer.answers.pop(0)
                if isinstance(answer, Exception):
                    raise answer
                return mock.Mock(text=answer)

        return Model()


class GeminiTests(unittest.TestCase):
    ENV = {"GEMINI_API_KEY": "k"}

    def run_with(self, answers, env=None, **kw):
        fake = FakeGemini(answers)
        google = mock.Mock(generativeai=fake)
        with mock.patch.dict(os.environ, {**self.ENV, **(env or {})}, clear=True), \
                mock.patch.dict(sys.modules, {"google": google, "google.generativeai": fake}):
            return fake, llm_client.llm_json("p", **kw)

    def test_gemini_3_5_flash_is_the_default_and_answers_in_json_mode(self):
        fake, out = self.run_with(['{"a": 1}'])
        self.assertEqual(out, {"a": 1})
        name, config = fake.built[0]
        self.assertEqual(name, "gemini-3.5-flash")
        self.assertEqual(config, {"response_mime_type": "application/json"})

    def test_temperature_is_left_at_googles_default_on_gemini_3_but_used_on_older_models(self):
        fake, _ = self.run_with(['{"a": 1}'], temperature=0)
        self.assertNotIn("temperature", fake.built[0][1])
        fake, _ = self.run_with(['{"a": 1}'], env={"GEMINI_MODEL": "gemini-2.5-flash"}, temperature=0)
        self.assertEqual(fake.built[0][1]["temperature"], 0)

    def test_a_pinned_model_can_be_chosen(self):
        fake, _ = self.run_with(['{"a": 1}'], env={"GEMINI_MODEL": "gemini-3.8-flash"})
        self.assertEqual(fake.built[0][0], "gemini-3.8-flash")

    def test_a_retired_model_falls_back_to_the_latest_alias_instead_of_failing(self):
        gone = RuntimeError("404 This model models/gemini-3.5-flash is no longer available")
        fake, out = self.run_with([gone, '{"ok": true}'])
        self.assertEqual(out, {"ok": True})
        self.assertEqual([b[0] for b in fake.built], ["gemini-3.5-flash", "gemini-flash-latest"])

    def test_a_busy_or_timed_out_gemini_is_asked_again_after_a_short_wait(self):
        busy = RuntimeError("503 The model is overloaded. Please try again later.")
        deadline = RuntimeError("DeadlineExceeded: 504 Deadline Exceeded")
        with mock.patch.object(llm_client.time, "sleep") as sleep:
            fake, out = self.run_with([busy, deadline, '{"ok": true}'])
        self.assertEqual(out, {"ok": True})
        self.assertEqual(len(fake.built), 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2.0, 4.0], "the pause grows")
        self.assertEqual({b[0] for b in fake.built}, {"gemini-3.5-flash"}, "the same model is asked, not another")

    def test_it_gives_up_after_three_busy_answers_and_a_non_busy_error_is_not_retried(self):
        busy = RuntimeError("429 Resource has been exhausted")
        with mock.patch.object(llm_client.time, "sleep"), self.assertRaisesRegex(RuntimeError, "Gemini request failed"):
            fake, _ = self.run_with([busy, busy, busy, '{"never": "reached"}'])
        with mock.patch.object(llm_client.time, "sleep") as sleep:
            fake = None
            with self.assertRaisesRegex(RuntimeError, "Gemini request failed"):
                fake, _ = self.run_with([ValueError("response was blocked"), '{"never": "reached"}'])
        sleep.assert_not_called()
        with mock.patch.object(llm_client.time, "sleep") as sleep, self.assertRaisesRegex(RuntimeError, "Gemini request failed"):
            self.run_with([busy, '{"never": "reached"}'], env={"GEMINI_ATTEMPTS": "1"})  # one attempt: no retry
        sleep.assert_not_called()

    def test_other_failures_do_not_try_another_model_and_become_a_runtime_error(self):
        fake = None
        with self.assertRaisesRegex(RuntimeError, "Gemini request failed"):
            fake, _ = self.run_with([ConnectionError("network down")])
        # a blocked or empty answer (the SDK raises ValueError on .text) is the same kind of failure
        with self.assertRaisesRegex(RuntimeError, "Gemini request failed"):
            self.run_with([ValueError("response was blocked")])

    def test_json_that_does_not_parse_is_asked_for_once_more(self):
        fake, out = self.run_with(["not json at all", '{"second": "try"}'])
        self.assertEqual(out, {"second": "try"})
        self.assertEqual(len(fake.calls), 2)
        with self.assertRaisesRegex(RuntimeError, "could not be read"):
            self.run_with(["nope", "still nope"])

    def test_a_request_never_waits_longer_than_the_callers_budget(self):
        fake, _ = self.run_with(['{"a": 1}'], budget_s=20)
        # NVIDIA is not configured here, so the whole budget is Gemini's
        self.assertLessEqual(fake.calls[0][1]["timeout"], 20)
        fake, _ = self.run_with(['{"a": 1}'])
        self.assertEqual(fake.calls[0][1]["timeout"], llm_client.GEMINI_TIMEOUT_S)

    def test_nvidia_failing_falls_back_to_gemini(self):
        fake = FakeGemini(['{"via": "gemini"}'])
        google = mock.Mock(generativeai=fake)
        env = {"NVIDIA_API_KEY": SECRET, "GEMINI_API_KEY": "k", "NVIDIA_MODELS": "m"}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("requests.post", return_value=_resp(503)), \
                mock.patch.dict(sys.modules, {"google": google, "google.generativeai": fake}):
            self.assertEqual(llm_client.llm_json("p"), {"via": "gemini"})
        llm_client._cooldown_until.clear()
        llm_client._timed_out.clear()


if __name__ == "__main__":
    unittest.main()
