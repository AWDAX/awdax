"""Hostile pages and files: exact host checks, linear-time HTML stripping, capped PDF downloads and parsing."""
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gazette_pdf  # noqa: E402
import gemini_scrape  # noqa: E402
from url_guard import host_is  # noqa: E402


class HostTests(unittest.TestCase):
    def test_only_the_real_host_or_its_subdomains(self):
        self.assertTrue(host_is("https://egazette.gov.in/x.pdf", "egazette.gov.in"))
        self.assertTrue(host_is("https://www.egazette.gov.in/", "egazette.gov.in"))
        for other in ("https://evil.example/?egazette.gov.in", "https://egazette.gov.in.evil.example/", "https://notegazette.gov.in/", "not a url"):
            self.assertFalse(host_is(other, "egazette.gov.in"), other)

    def test_tls_checks_stay_on_for_lookalike_pdf_urls(self):
        sess = mock.Mock()
        with mock.patch("gazette_pdf.safe_get", side_effect=gazette_pdf.requests.exceptions.SSLError("bad cert")) as get, \
                self.assertRaises(gazette_pdf.requests.exceptions.SSLError):
            gazette_pdf._fetch_pdf_bytes(sess, "https://evil.example/egazette.gov.in/x.pdf")
        self.assertEqual([c.kwargs["verify"] for c in get.call_args_list], [gazette_pdf._pdf_verify_option()])
        self.assertEqual(get.call_args.kwargs["max_bytes"], gazette_pdf.MAX_PDF_BYTES)


class StripTests(unittest.TestCase):
    def test_scripts_and_styles_go_text_stays(self):
        html = "<p>a</p><script type='x'>bad()</script><scripted>keep</scripted><STYLE>.c{}</STYLE><p>b</p><script>never closed"
        self.assertEqual(gemini_scrape._strip_scripts_styles(html), "<p>a</p> <scripted>keep</scripted> <p>b</p>")

    def test_many_unclosed_tags_stay_fast(self):
        hostile = "<script>" * 50_000 + "x" * 100_000
        t = time.perf_counter()
        gemini_scrape._strip_scripts_styles(hostile)
        self.assertLess(time.perf_counter() - t, 1.0)


class PdfTests(unittest.TestCase):
    @unittest.skipUnless(gazette_pdf.PYMUPDF_AVAILABLE, "needs PyMuPDF")
    def test_only_the_first_pages_are_read(self):
        doc = gazette_pdf.fitz.open()
        for i in range(gazette_pdf.MAX_PDF_PAGES + 5):
            doc.new_page().insert_text((72, 72), f"page {i}")
        text = gazette_pdf.pdf_text(doc.tobytes())
        self.assertIn(f"page {gazette_pdf.MAX_PDF_PAGES - 1}", text)
        self.assertNotIn(f"page {gazette_pdf.MAX_PDF_PAGES}", text)


if __name__ == "__main__":
    unittest.main()
