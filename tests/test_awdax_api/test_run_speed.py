"""Run time: live runs report "running" from the start, timed-out models don't cost a timeout on every call,
and a page that never finishes loading can't hold a browser for minutes."""
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

import browser  # noqa: E402
import inspector  # noqa: E402
import llm_client  # noqa: E402
import scraper  # noqa: E402
import plan_scraper  # noqa: E402

SECRET = "nvapi-SECRET-VALUE"


def _resp(status=200, content=""):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = {"choices": [{"message": {"content": content}}]}
    return r


class LiveStartTests(unittest.TestCase):
    """The orchestrator waits while is_job_running(); a live start must count as running before its thread runs."""

    def setUp(self):
        self.svc = scraper.UniversalScrapeService()
        for name in ("save_job", "_set_status", "emit_event"):
            p = mock.patch.object(self.svc, name)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.svc, "get_scrape_status", return_value={})
        p.start()
        self.addCleanup(p.stop)
        self.job = mock.Mock(job_id="job-1")

    def test_live_start_counts_as_running_before_the_first_cycle(self):
        cycle = threading.Event()
        release = threading.Event()

        def run_all(*args, **kwargs):
            cycle.set()
            release.wait(5)

        with mock.patch.object(self.svc, "_run_all", side_effect=run_all):
            with mock.patch.object(threading.Thread, "start"):
                # The thread never runs here: whatever the orchestrator would see right after start_live is what counts.
                self.svc.start_live([], self.job)
                self.assertTrue(self.svc.is_job_running("job-1"))

    def test_live_job_stops_counting_once_its_loop_ends(self):
        with mock.patch.object(self.svc, "_run_all"), mock.patch.dict(os.environ, {"LIVE_SCRAPE_INTERVAL_SEC": "15"}):
            self.svc.start_live([], self.job)
            self.svc.stop_live("job-1")
            runner_thread = [t for t in threading.enumerate() if t.name.startswith("live-scrape-job-1")]
            for t in runner_thread:
                t.join(5)
        self.assertFalse(self.svc.is_job_running("job-1"))

    def test_live_job_stopped_before_its_first_cycle_does_not_stay_running(self):
        with mock.patch.object(threading.Thread, "start"):
            self.svc.start_live([], self.job)
        self.svc._live["job-1"].stop.set()
        self.svc._live_loop("job-1")
        self.assertFalse(self.svc.is_job_running("job-1"))


class TimedOutModelTests(unittest.TestCase):
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

    def test_after_every_model_timed_out_a_call_tries_only_one(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "a,b,c"}
        replies = [requests.Timeout("t")] * 3 + [_resp(200, '{"ok": 1}')]
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("requests.post", side_effect=replies) as post:
            with self.assertRaises(RuntimeError):
                llm_client.llm_json("p")
            self.assertEqual(llm_client.llm_json("p"), {"ok": 1})
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["a", "b", "c", "a"])

    def test_busy_models_still_come_before_a_timed_out_one(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "a,b,c"}
        replies = [requests.Timeout("t"), _resp(503), _resp(503), _resp(503), _resp(503), _resp(200, '{"ok": 1}')]
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("requests.post", side_effect=replies) as post:
            with self.assertRaises(RuntimeError):
                llm_client.llm_json("p")
            self.assertEqual(llm_client.llm_json("p"), {"ok": 1})
        self.assertEqual([c.kwargs["json"]["model"] for c in post.call_args_list], ["a", "b", "c", "b", "c", "a"])

    def test_a_model_that_answers_again_is_no_longer_held_back(self):
        env = {"NVIDIA_API_KEY": SECRET, "NVIDIA_MODELS": "a,b"}
        replies = [requests.Timeout("t"), requests.Timeout("t"), _resp(200, '{"n": 1}'), _resp(200, '{"n": 2}')]
        with mock.patch.dict(os.environ, env, clear=True), mock.patch("requests.post", side_effect=replies):
            with self.assertRaises(RuntimeError):
                llm_client.llm_json("p")
            llm_client.llm_json("p")
        self.assertNotIn("a", llm_client._timed_out)


class PageLoadTests(unittest.TestCase):
    def setUp(self):
        # load_page now vets the URL (DNS) and the page Chrome landed on (SSRF guard); these tests are about timing.
        for name in ("check_url", "check_browser_url"):
            patcher = mock.patch.object(inspector, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_page_that_never_finishes_loading_is_stopped_and_read_as_is(self):
        driver = mock.Mock()
        driver.get.side_effect = inspector.TimeoutException("slow")
        inspector.load_page(driver, "https://example.test/")
        driver.execute_script.assert_called_once_with("window.stop();")

    def test_a_page_that_loads_is_left_alone(self):
        driver = mock.Mock()
        inspector.load_page(driver, "https://example.test/")
        driver.get.assert_called_once_with("https://example.test/")
        driver.execute_script.assert_not_called()

    def test_every_browser_gets_a_page_load_limit(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(browser.webdriver, "Chrome") as chrome:
                inspector._setup_driver()
            chrome.return_value.set_page_load_timeout.assert_called_once_with(45)
            with mock.patch.object(browser.webdriver, "Chrome") as chrome:
                plan_scraper.PlanDrivenScraper(mock.Mock(column_map={})).setup_driver()
            chrome.return_value.set_page_load_timeout.assert_called_once_with(45)

    def test_chrome_starts_the_same_way_everywhere_and_a_server_can_name_its_browser(self):
        with mock.patch.dict(os.environ, {"CHROME_BIN": "/usr/bin/chromium", "CHROMEDRIVER_PATH": "/usr/bin/chromedriver"}, clear=True),                 mock.patch.object(browser.webdriver, "Chrome") as chrome:
            browser.launch(capture_network=True, hide_automation=True)
        options = chrome.call_args.kwargs["options"]
        self.assertEqual(options.binary_location, "/usr/bin/chromium")
        self.assertEqual(chrome.call_args.kwargs["service"].path, "/usr/bin/chromedriver")
        args = options.arguments
        for flag in ("--no-sandbox", "--disable-dev-shm-usage", "--headless=new", "--window-size=1920,1080"):
            self.assertIn(flag, args)
        self.assertIn("--disable-blink-features=AutomationControlled", args)
        self.assertEqual(options.capabilities["goog:loggingPrefs"], {"performance": "ALL"})
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(browser.webdriver, "Chrome") as chrome:
            browser.launch(headless=False)
        self.assertNotIn("service", chrome.call_args.kwargs)
        self.assertNotIn("--headless=new", chrome.call_args.kwargs["options"].arguments)


if __name__ == "__main__":
    unittest.main()
