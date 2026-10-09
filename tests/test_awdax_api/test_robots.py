"""robots.txt is respected: disallowed pages are skipped with the reason; RFC 9309 rules for missing/broken files."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import discovery  # noqa: E402
import inspector  # noqa: E402
import robots  # noqa: E402
from robots import RobotsDisallowed, check_robots  # noqa: E402

TXT = "User-agent: *\nDisallow: /private/\n"
# A group naming AWDAX replaces the `*` group for it (the standard): /private/ is allowed here, /no-awdax/ isn't.
TXT_NAMED = "User-agent: *\nDisallow: /private/\n\nUser-agent: AWDAX\nDisallow: /no-awdax/\n"


def _resp(status=200, text=TXT):
    r = mock.Mock()
    r.status_code = status
    r.text = text
    return r


class RobotsTests(unittest.TestCase):
    def setUp(self):
        robots._cache.clear()
        self.addCleanup(robots._cache.clear)

    def test_rules_for_everyone_are_honoured_and_cached_per_site(self):
        with mock.patch("robots.safe_get", return_value=_resp()) as get:
            check_robots("https://site.example/cars")
            with self.assertRaises(RobotsDisallowed):
                check_robots("https://site.example/private/x")
        get.assert_called_once()  # one robots.txt per site, cached
        self.assertEqual(get.call_args.args[0], "https://site.example/robots.txt")

    def test_a_group_naming_awdax_is_the_one_that_applies(self):
        with mock.patch("robots.safe_get", return_value=_resp(text=TXT_NAMED)):
            check_robots("https://named.example/private/x")
            with self.assertRaises(RobotsDisallowed):
                check_robots("https://named.example/no-awdax/y")

    def test_missing_file_allows_and_server_error_or_no_answer_disallows(self):
        with mock.patch("robots.safe_get", return_value=_resp(404, "")):
            check_robots("https://a.example/anything")
        with mock.patch("robots.safe_get", return_value=_resp(503, "")), self.assertRaises(RobotsDisallowed):
            check_robots("https://b.example/anything")
        with mock.patch("robots.safe_get", side_effect=TimeoutError("t")), self.assertRaises(RobotsDisallowed):
            check_robots("https://c.example/anything")

    def test_a_failed_fetch_is_retried_after_a_minute_not_an_hour(self):
        with mock.patch("robots.time.monotonic", return_value=1000.0):
            with mock.patch("robots.safe_get", side_effect=TimeoutError("t")), self.assertRaises(RobotsDisallowed):
                check_robots("https://d.example/x")
        with mock.patch("robots.time.monotonic", return_value=1000.0 + robots.FAILED_TTL_S + 1):
            with mock.patch("robots.safe_get", return_value=_resp()):
                check_robots("https://d.example/x")

    def test_the_cache_stays_bounded(self):
        with mock.patch.object(robots, "MAX_SITES", 3), mock.patch("robots.safe_get", return_value=_resp()):
            for i in range(10):
                check_robots(f"https://s{i}.example/x")
        self.assertLessEqual(len(robots._cache), 3)

    def test_a_disallowed_page_is_a_skipped_source_with_the_reason(self):
        with mock.patch("robots.safe_get", return_value=_resp()), mock.patch("discovery.safe_get") as page_get:
            out = discovery.fetch_html("https://site.example/private/list")
        page_get.assert_not_called()
        self.assertTrue(out["blocked"])
        self.assertIn("robots.txt", out["error"])

    def test_the_browser_never_opens_a_disallowed_page(self):
        driver = mock.Mock()
        with mock.patch("inspector.check_url"), mock.patch("robots.safe_get", return_value=_resp()), self.assertRaises(RobotsDisallowed):
            inspector.load_page(driver, "https://site.example/private/list")
        driver.get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
