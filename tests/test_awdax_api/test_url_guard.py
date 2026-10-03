"""SSRF guard (BE-04): user/LLM-chosen URLs must never reach loopback, private, link-local or metadata addresses,
not directly, not through a redirect, and not through the headless browser. No real network is used."""
import ipaddress
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from requests.structures import CaseInsensitiveDict  # noqa: E402

import discovery  # noqa: E402
import inspector  # noqa: E402
import gazette_pdf  # noqa: E402
import plan_scraper  # noqa: E402
import url_guard  # noqa: E402

PUBLIC = "93.184.216.34"
ENV = "AWDAX_ALLOW_PRIVATE_URLS"


def _addrinfo(ip: str):
    fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return (fam, socket.SOCK_STREAM, 6, "", (ip, 0))


def _fake_getaddrinfo(table: dict[str, list[str]] | None = None):
    """Name table first; otherwise behave like the resolver does for numeric hosts (including 2130706433, 0x7f.1)."""
    table = table or {}

    def gai(host, port=None, *args, **kwargs):
        if host in table:
            return [_addrinfo(ip) for ip in table[host]]
        try:
            return [_addrinfo(str(ipaddress.ip_address(host)))]
        except ValueError:
            pass
        try:
            return [_addrinfo(socket.inet_ntoa(socket.inet_aton(host)))]
        except OSError:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    return gai


class _Resp:
    """Just enough of requests.Response for safe_get."""

    def __init__(self, url, status=200, location=None, body=b"", chunk=1000):
        self.url = url
        self.status_code = status
        self.headers = CaseInsensitiveDict({"Location": location} if location else {})
        self._body = body
        self._chunk = chunk
        self._content = False
        self._content_consumed = False
        self.closed = False
        self.bytes_served = 0

    def iter_content(self, chunk_size=1, decode_unicode=False):
        size = max(chunk_size, self._chunk)
        for i in range(0, len(self._body), size):
            part = self._body[i : i + size]
            self.bytes_served += len(part)
            yield part

    @property
    def content(self):
        if self._content is False:
            self._content = b"".join(self.iter_content(10**9))
            self._content_consumed = True
        return self._content

    @property
    def text(self):
        return self.content.decode("utf-8", errors="replace")

    def close(self):
        self.closed = True


class GuardTestCase(unittest.TestCase):
    names: dict[str, list[str]] = {}

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(ENV, None)
        gai = mock.patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo(self.names))
        gai.start()
        self.addCleanup(gai.stop)


class CheckUrlRejectTests(GuardTestCase):
    names = {
        "localhost": ["127.0.0.1", "::1"],
        "mixed.example": [PUBLIC, "10.0.0.5"],
        "mixed6.example": ["2606:2800:220:1:248:1893:25c8:1946", "fc00::1"],
        "meta.example": ["169.254.169.254"],
    }

    def test_unsafe_urls_are_rejected(self):
        bad = [
            "http://127.0.0.1/",
            "https://127.0.0.1:8443/x",
            "http://localhost/",
            "http://localhost:5000/api",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://100.64.0.1/",
            "http://[::1]/",
            "http://[fc00::1]/",
            "http://[fe80::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://[::ffff:169.254.169.254]/",
            "http://0.0.0.0/",
            "http://224.0.0.1/",
            "http://good.example@127.0.0.1/",
            "http://good.example:pw@169.254.169.254/",
            "http://mixed.example/",
            "http://mixed6.example/",
            "http://meta.example/",
            "http://2130706433/",  # decimal 127.0.0.1
            "http://0x7f.1/",  # hex/short form
            "http://0177.0.0.1/",  # octal
            "http://127.1/",
        ]
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(url_guard.UnsafeURL):
                    url_guard.check_url(url)

    def test_bad_schemes_and_hosts_are_rejected(self):
        bad = [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "javascript:alert(1)",
            "gopher://example.com/",
            "data:text/html,hi",
            "http:///nohost",
            "http://",
            "",
            "   ",
            "example.com/no-scheme",
            "http://exa mple.com/",
            "http://example.com:notaport/",
        ]
        for url in bad:
            with self.subTest(url=url):
                with self.assertRaises(url_guard.UnsafeURL):
                    url_guard.check_url(url)

    def test_non_string_is_rejected(self):
        with self.assertRaises(url_guard.UnsafeURL):
            url_guard.check_url(None)  # type: ignore[arg-type]

    def test_unresolvable_host_is_unsafe(self):
        with self.assertRaises(url_guard.UnsafeURL) as cm:
            url_guard.check_url("http://nope.invalid/")
        self.assertIn("could not resolve host", str(cm.exception))

    def test_error_text_does_not_leak_resolved_address(self):
        with self.assertRaises(url_guard.UnsafeURL) as cm:
            url_guard.check_url("http://meta.example/")
        self.assertNotIn("169.254", str(cm.exception))
        self.assertEqual(str(cm.exception), "Blocked: address not allowed")


class CheckUrlAllowTests(GuardTestCase):
    names = {"example.test": [PUBLIC], "dual.test": [PUBLIC, "2606:2800:220:1:248:1893:25c8:1946"]}

    def test_public_ip_and_names_are_allowed_and_returned_unchanged(self):
        for url in (
            f"http://{PUBLIC}/",
            f"https://{PUBLIC}:8443/a?b=c#d",
            "https://example.test/path?q=1",
            "http://dual.test/",
            "HTTPS://example.test/",
        ):
            with self.subTest(url=url):
                self.assertEqual(url_guard.check_url(url), url)

    def test_the_check_runs_on_resolved_addresses_for_every_family(self):
        with mock.patch("socket.getaddrinfo", side_effect=_fake_getaddrinfo(self.names)) as gai:
            url_guard.check_url("https://example.test/")
        gai.assert_called_once()
        self.assertEqual(gai.call_args.args[0], "example.test")


class CheckUrlEnvBypassTests(GuardTestCase):
    def test_bypass_allows_private_addresses_but_not_bad_schemes(self):
        os.environ[ENV] = "1"
        self.assertEqual(url_guard.check_url("http://127.0.0.1:5000/x"), "http://127.0.0.1:5000/x")
        self.assertEqual(url_guard.check_url("http://localhost/"), "http://localhost/")
        for url in ("file:///etc/passwd", "ftp://x", "javascript:alert(1)", "http:///nohost"):
            with self.subTest(url=url):
                with self.assertRaises(url_guard.UnsafeURL):
                    url_guard.check_url(url)

    def test_other_values_do_not_bypass(self):
        for value in ("", "0", "no"):
            os.environ[ENV] = value
            with self.subTest(value=value):
                with self.assertRaises(url_guard.UnsafeURL):
                    url_guard.check_url("http://127.0.0.1/")


class SafeGetTests(GuardTestCase):
    names = {"a.test": [PUBLIC], "b.test": ["93.184.216.35"]}

    def _get(self, responses, **kw):
        """Run safe_get with requests.get replaced by a scripted sequence; returns (result, calls)."""
        seq = list(responses)
        calls = []

        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return seq.pop(0)

        with mock.patch("requests.get", side_effect=fake_get):
            try:
                result = url_guard.safe_get(**kw)
            except Exception as exc:  # noqa: BLE001 - tests inspect it
                result = exc
        return result, calls

    def test_plain_get_disables_requests_redirects_and_keeps_caller_kwargs(self):
        ok = _Resp("https://a.test/", body=b"hello")
        result, calls = self._get(
            [ok], url="https://a.test/", timeout=25, verify=False, headers={"X": "1"}
        )
        self.assertIs(result, ok)
        self.assertEqual(result.content, b"hello")
        (url, kwargs), = calls
        self.assertEqual(url, "https://a.test/")
        self.assertIs(kwargs["allow_redirects"], False)
        self.assertIs(kwargs["stream"], True)
        self.assertEqual(kwargs["timeout"], 25)
        self.assertIs(kwargs["verify"], False)
        self.assertEqual(kwargs["headers"], {"X": "1"})

    def test_a_caller_cannot_turn_redirect_following_back_on(self):
        _, calls = self._get([_Resp("https://a.test/")], url="https://a.test/", allow_redirects=True)
        self.assertIs(calls[0][1]["allow_redirects"], False)

    def test_redirect_to_the_metadata_service_is_stopped_before_any_request_to_it(self):
        chain = [_Resp("https://a.test/", 302, location="http://169.254.169.254/latest/meta-data/")]
        result, calls = self._get(chain, url="https://a.test/")
        self.assertIsInstance(result, url_guard.UnsafeURL)
        self.assertEqual([c[0] for c in calls], ["https://a.test/"])
        self.assertTrue(chain[0].closed)

    def test_redirect_through_a_second_public_hop_to_private_is_stopped(self):
        chain = [
            _Resp("https://a.test/", 301, location="https://b.test/next"),
            _Resp("https://b.test/next", 307, location="http://127.0.0.1:8080/admin"),
        ]
        result, calls = self._get(chain, url="https://a.test/")
        self.assertIsInstance(result, url_guard.UnsafeURL)
        self.assertEqual([c[0] for c in calls], ["https://a.test/", "https://b.test/next"])

    def test_redirect_to_a_non_http_scheme_is_stopped(self):
        chain = [_Resp("https://a.test/", 302, location="file:///etc/passwd")]
        result, calls = self._get(chain, url="https://a.test/")
        self.assertIsInstance(result, url_guard.UnsafeURL)
        self.assertEqual(len(calls), 1)

    def test_relative_redirects_are_resolved_against_the_current_url(self):
        chain = [
            _Resp("https://a.test/dir/page", 302, location="../other?x=1"),
            _Resp("https://a.test/other?x=1", 302, location="/abs"),
            _Resp("https://a.test/abs", 200, body=b"done"),
        ]
        result, calls = self._get(chain, url="https://a.test/dir/page")
        self.assertEqual([c[0] for c in calls], ["https://a.test/dir/page", "https://a.test/other?x=1", "https://a.test/abs"])
        self.assertEqual(result.content, b"done")
        self.assertEqual(result.url, "https://a.test/abs")

    def test_relative_redirect_stays_on_the_checked_host(self):
        chain = [_Resp("https://a.test/", 302, location="//127.0.0.1/x")]
        result, calls = self._get(chain, url="https://a.test/")
        self.assertIsInstance(result, url_guard.UnsafeURL)
        self.assertEqual(len(calls), 1)

    def test_redirect_limit(self):
        loop = [_Resp("https://a.test/", 302, location="https://a.test/") for _ in range(10)]
        result, calls = self._get(loop, url="https://a.test/", max_redirects=3)
        self.assertIsInstance(result, requests.TooManyRedirects)
        self.assertEqual(len(calls), 4)  # the first request plus three followed hops

    def test_redirect_status_without_location_is_returned_as_is(self):
        odd = _Resp("https://a.test/", 304)
        result, _ = self._get([odd], url="https://a.test/")
        self.assertIs(result, odd)

    def test_the_first_url_is_checked_too(self):
        result, calls = self._get([], url="http://127.0.0.1/")
        self.assertIsInstance(result, url_guard.UnsafeURL)
        self.assertEqual(calls, [])

    def test_max_bytes_truncates_a_large_streamed_body_without_reading_it_all(self):
        big = _Resp("https://a.test/", body=b"x" * 5_000_000, chunk=8192)
        result, _ = self._get([big], url="https://a.test/", max_bytes=100_000)
        self.assertEqual(len(result.content), 100_000)
        self.assertEqual(len(result.text), 100_000)
        self.assertLess(big.bytes_served, 200_000)
        self.assertTrue(big.closed)

    def test_max_bytes_leaves_a_small_body_whole(self):
        small = _Resp("https://a.test/", body=b"tiny")
        result, _ = self._get([small], url="https://a.test/", max_bytes=100_000)
        self.assertEqual(result.content, b"tiny")

    def test_session_is_used_when_given(self):
        sess = mock.Mock()
        sess.get.return_value = _Resp("https://a.test/", body=b"s")
        with mock.patch("requests.get") as plain:
            result = url_guard.safe_get("https://a.test/", session=sess, timeout=5)
        plain.assert_not_called()
        self.assertEqual(result.content, b"s")
        self.assertIs(sess.get.call_args.kwargs["allow_redirects"], False)


class CheckBrowserUrlTests(GuardTestCase):
    names = {"a.test": [PUBLIC], "inner.test": ["10.1.2.3"]}

    def test_a_driver_that_ended_up_on_an_internal_address_is_rejected(self):
        for url in (
            "http://169.254.169.254/latest/meta-data/",
            "http://inner.test/admin",
            "http://localhost:8000/",
            "file:///etc/passwd",
            "chrome://settings",
            "view-source:http://a.test/",
            "",
        ):
            with self.subTest(url=url):
                driver = mock.Mock()
                driver.current_url = url
                with self.assertRaises(url_guard.UnsafeURL):
                    url_guard.check_browser_url(driver)

    def test_a_public_page_passes(self):
        driver = mock.Mock()
        driver.current_url = "https://a.test/listing?page=2"
        url_guard.check_browser_url(driver)

    def test_a_blank_page_holds_nothing_and_passes(self):
        driver = mock.Mock()
        driver.current_url = "about:blank"
        url_guard.check_browser_url(driver)


class DiscoveryCallSiteTests(GuardTestCase):
    names = {"example.test": [PUBLIC], "localhost": ["127.0.0.1", "::1"]}
    HTML = "<html><title>Hi</title>" + "<table><tr><th>A</th></tr></table>" + ("x" * 600) + "</html>"

    def test_fetch_html_reports_a_blocked_source_instead_of_raising(self):
        with mock.patch("discovery.safe_get", side_effect=url_guard.UnsafeURL("Blocked: address not allowed")) as sg:
            out = discovery.fetch_html("https://example.test/")
        self.assertFalse(out["https_ok"])
        self.assertEqual(out["error"], "Blocked: address not allowed")
        self.assertTrue(out["blocked"])
        self.assertEqual(sg.call_count, 1, "no verify=False retry for a blocked address")

    def test_fetch_html_blocks_a_redirect_to_the_metadata_service(self):
        hop = _Resp("https://example.test/", 302, location="http://169.254.169.254/latest/meta-data/")
        with mock.patch("requests.get", return_value=hop) as get:
            out = discovery.fetch_html("https://example.test/")
        self.assertEqual(get.call_count, 1)
        self.assertFalse(out["https_ok"])
        self.assertTrue(out["blocked"])
        self.assertEqual(out["error"], "Blocked: address not allowed")
        self.assertEqual(out["html"], "")

    def test_fetch_html_blocks_private_hosts_without_any_request(self):
        for url in ("https://127.0.0.1/", "http://localhost:5000/", "https://10.0.0.5/x", "http://169.254.169.254/"):
            with self.subTest(url=url), mock.patch("requests.get") as get:
                out = discovery.fetch_html(url)
            get.assert_not_called()
            self.assertFalse(out["https_ok"])
            self.assertTrue(out["blocked"], url)

    def test_probe_https_passes_the_blocked_flag_on(self):
        with mock.patch("discovery.safe_get", side_effect=url_guard.UnsafeURL("Blocked: address not allowed")):
            probe = discovery.probe_https("https://example.test/")
        self.assertTrue(probe["blocked"])
        self.assertEqual(probe["error"], "Blocked: address not allowed")

    def test_unresolvable_host_is_a_failure_not_a_block(self):
        with mock.patch("requests.get") as get:
            out = discovery.fetch_html("https://nope.invalid/")
        get.assert_not_called()
        self.assertFalse(out["blocked"])
        self.assertIn("could not resolve host", out["error"])

    def test_a_safe_url_behaves_as_before(self):
        body = self.HTML.encode()
        resp = _Resp("https://example.test/final", 200, body=body)
        with mock.patch("requests.get", return_value=resp) as get:
            out = discovery.fetch_html("https://example.test/")
        self.assertTrue(out["https_ok"])
        self.assertFalse(out["blocked"])
        self.assertEqual(out["final_url"], "https://example.test/final")
        self.assertEqual(out["http_status"], 200)
        self.assertEqual(out["title"], "Hi")
        self.assertEqual(out["table_count"], 1)
        self.assertEqual(out["table_headers_preview"], ["A"])
        kwargs = get.call_args.kwargs
        self.assertEqual(kwargs["timeout"], 25)
        self.assertIn("User-Agent", kwargs["headers"])

    def test_the_body_read_is_bounded_by_the_truncation_size(self):
        huge = _Resp("https://example.test/", 200, body=b"<p>" + b"x" * 3_000_000, chunk=8192)
        with mock.patch("requests.get", return_value=huge):
            out = discovery.fetch_html("https://example.test/", max_chars=50_000)
        self.assertEqual(len(out["html"]), 50_000)
        self.assertLess(huge.bytes_served, 500_000)

    def test_a_connection_error_still_takes_the_existing_error_path(self):
        with mock.patch("requests.get", side_effect=requests.ConnectionError("boom")) as get:
            out = discovery.fetch_html("https://example.test/")
        self.assertEqual(get.call_count, 2, "the existing verify=False retry is unchanged")
        self.assertFalse(out["blocked"])
        self.assertIn("boom", out["error"])


class InspectorCallSiteTests(GuardTestCase):
    names = {"example.test": [PUBLIC], "inner.test": ["10.1.2.3"]}

    def test_load_page_refuses_unsafe_urls_before_touching_the_browser(self):
        for url in ("file:///etc/passwd", "http://127.0.0.1/", "http://169.254.169.254/", "http://inner.test/", "javascript:1"):
            with self.subTest(url=url):
                driver = mock.Mock()
                with self.assertRaises(url_guard.UnsafeURL):
                    inspector.load_page(driver, url)
                driver.get.assert_not_called()

    def test_load_page_rejects_a_page_chrome_redirected_to_an_internal_address(self):
        driver = mock.Mock()
        driver.current_url = "http://169.254.169.254/latest/meta-data/"
        with self.assertRaises(url_guard.UnsafeURL):
            inspector.load_page(driver, "https://example.test/")
        driver.get.assert_called_once_with("https://example.test/")

    def test_load_page_checks_the_final_url_after_a_timeout_stop_too(self):
        driver = mock.Mock()
        driver.get.side_effect = inspector.TimeoutException("slow")
        driver.current_url = "http://10.0.0.5/"
        with self.assertRaises(url_guard.UnsafeURL):
            inspector.load_page(driver, "https://example.test/")

    def test_load_page_lets_a_safe_page_through(self):
        driver = mock.Mock()
        driver.current_url = "https://example.test/landed"
        inspector.load_page(driver, "https://example.test/")
        driver.get.assert_called_once_with("https://example.test/")

    def test_a_blocked_probe_becomes_a_blocked_plan_without_starting_a_browser(self):
        blocked = {"https_ok": False, "blocked": True, "error": "Blocked: address not allowed", "final_url": "https://x/"}
        src = discovery.SourceCandidate(url="https://example.test/", title="T", domain="example.test")
        intent = mock.Mock()
        with mock.patch("inspector.probe_https", return_value=blocked), \
                mock.patch("inspector._probe_page_selenium") as sel:
            plan = inspector.inspect_source(intent, src)
        sel.assert_not_called()
        self.assertTrue(plan.blocked)
        self.assertEqual(plan.confidence, 0.0)
        self.assertIn("Blocked: address not allowed", " ".join(plan.warnings))

    def test_an_ordinary_failed_probe_is_rejected_with_its_own_reason_not_as_an_address_block(self):
        # Since d822c4e a source unreachable over HTTPS is rejected at inspect; it must never read as an SSRF block.
        failed = {"https_ok": False, "blocked": False, "error": "HTTP 500", "final_url": "https://x/"}
        src = discovery.SourceCandidate(url="https://example.test/", title="T", domain="example.test")
        with mock.patch("inspector.probe_https", return_value=failed):
            plan = inspector.inspect_source(mock.Mock(), src)
        self.assertTrue(plan.blocked)
        self.assertIn("HTTP 500", " ".join(plan.warnings))
        self.assertNotIn("Blocked:", " ".join(plan.warnings))


class ScraperCallSiteTests(GuardTestCase):
    names = {"example.test": [PUBLIC]}

    def test_open_entry_refuses_an_internal_entry_url(self):
        for url in ("http://169.254.169.254/latest/meta-data/", "file:///etc/passwd", "http://127.0.0.1:8000/api"):
            with self.subTest(url=url):
                s = plan_scraper.PlanDrivenScraper(inspector.ScrapePlan(source_name="s", entry_url=url))
                s.driver = mock.Mock()
                with self.assertRaises(url_guard.UnsafeURL) as cm:
                    s.open_entry()
                s.driver.get.assert_not_called()
                self.assertEqual(str(cm.exception)[:8], "Blocked:")

    def test_a_blocked_source_is_one_failed_source_not_a_crashed_run(self):
        # _run_all records "<source>: <reason>" for any per-source exception and carries on; the reason must be short.
        plan = inspector.ScrapePlan(source_name="Evil", entry_url="http://169.254.169.254/")
        s = plan_scraper.PlanDrivenScraper(plan)
        s.driver = mock.Mock()
        try:
            s.open_entry()
        except Exception as exc:  # noqa: BLE001
            text = f"{plan.source_name}: {exc}"
        self.assertEqual(text, "Evil: Blocked: address not allowed")

    def test_template_pdf_urls_to_internal_addresses_are_dropped(self):
        self.assertEqual(plan_scraper.guard_detail_url("http://169.254.169.254/x.pdf"), "")
        self.assertEqual(plan_scraper.guard_detail_url("file:///etc/passwd"), "")
        self.assertEqual(plan_scraper.guard_detail_url("https://example.test/a.pdf"), "https://example.test/a.pdf")
        self.assertEqual(plan_scraper.guard_detail_url(""), "")


class RegulatoryPdfDownloadTests(GuardTestCase):
    def test_pdf_download_refuses_an_internal_url_without_requesting_it(self):
        sess = mock.Mock()
        for url in ("http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8000/api/feed", "file:///etc/passwd"):
            with self.subTest(url=url):
                with self.assertRaises(url_guard.UnsafeURL):
                    gazette_pdf._fetch_pdf_bytes(sess, url, timeout=5)
        sess.get.assert_not_called()

    def test_pymupdf_loads(self):
        # The import is optional (try/except), so a renamed module would silently fall back to pdfminer.
        self.assertTrue(gazette_pdf.PYMUPDF_AVAILABLE)


if __name__ == "__main__":
    unittest.main()
