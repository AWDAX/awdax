"""eGazette PDFs: fetch (SSRF-checked), text extraction and the Hindi filter (from RegulatoryFeed.py)."""

import io
import logging
import os
import re
import time
from typing import Any

import requests

from url_guard import host_is, safe_get

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment,misc]


try:
    import pymupdf as fitz  # PyMuPDF; its old module name "fitz" is deprecated
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Hindi / non-Latin filter
# ---------------------------------------------------------------------------

HINDI_RANGES = [
    (0x0900, 0x097F), (0x0980, 0x09FF), (0x0A00, 0x0A7F),
    (0x0A80, 0x0AFF), (0x0B00, 0x0B7F), (0x0B80, 0x0BFF),
    (0x0C00, 0x0C7F), (0x0C80, 0x0CFF), (0x0D00, 0x0D7F),
    (0x0D80, 0x0DFF), (0x0E00, 0x0E7F), (0x0E80, 0x0EFF),
    (0x0F00, 0x0FFF), (0x1CD0, 0x1CFF), (0xA8E0, 0xA8FF),
]

def _is_hindi(char: str) -> bool:
    cp = ord(char)
    return any(s <= cp <= e for s, e in HINDI_RANGES)

def filter_hindi_text(text: str) -> str:
    if not text:
        return ""
    filtered = "".join(c for c in text if not _is_hindi(c))
    lines = [ln.strip() for ln in filtered.split("\n") if ln.strip() and any(c.isalpha() for c in ln)]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

_PDF_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _pdf_verify_option():
    if certifi is not None:
        return certifi.where()
    return True


def _fetch_pdf_bytes(
    sess: requests.Session,
    pdf_url: str,
    *,
    timeout: int = 30,
) -> bytes | None:
    """Download PDF bytes; retry without verify for egazette on macOS SSL issues."""
    verify_opts: list[Any] = [_pdf_verify_option()]
    # The real host only: "egazette.gov.in" anywhere else in a URL (a query, a path) must not switch TLS checks off.
    if host_is(pdf_url or "", "egazette.gov.in"):
        verify_opts.append(False)
    last_err: Exception | None = None
    for verify in verify_opts:
        try:
            # The URL can come from an LLM-written template or a scraped viewer page: every hop is checked (SSRF).
            resp = safe_get(pdf_url, session=sess, timeout=timeout, verify=verify, max_bytes=MAX_PDF_BYTES)
            if resp.status_code == 200 and len(resp.content) >= 100:
                return resp.content
            return None
        except requests.exceptions.SSLError as e:
            last_err = e
            if verify is False:
                break
            continue
        except Exception as e:
            last_err = e
            break
    if last_err:
        raise last_err
    return None


def _scrape_fast_mode() -> bool:
    return os.getenv("SCRAPE_FAST", "1").strip().lower() in ("1", "true", "yes")


def guess_pdf_url(gazette_id: str) -> str:
    """Best-effort PDF URL from gazette ID (avoids slow Selenium PDF clicks)."""
    gid = (gazette_id or "").strip()
    if not gid:
        return ""
    num_m = re.search(r"-(\d+)\s*$", gid)
    if not num_m:
        return ""
    num = num_m.group(1)
    year = str(time.gmtime().tm_year)
    date_m = re.search(r"-(\d{8})-\d+$", gid)
    if date_m:
        year = date_m.group(1)[4:8]
    else:
        year_m = re.search(r"(20\d{2})", gid)
        if year_m:
            year = year_m.group(1)
    return f"https://egazette.gov.in/WriteReadData/{year}/{num}.pdf"


def _pdf_session(cookies_sess: requests.Session | None = None) -> requests.Session:
    sess = cookies_sess or requests.Session()
    sess.headers.setdefault("User-Agent", _PDF_UA)
    return sess


MAX_PDF_BYTES = 20 * 2**20
MAX_PDF_PAGES = 200


def pdf_text(pdf_bytes: bytes) -> str:
    """The text of a PDF (PyMuPDF, else pdfminer), from at most its first MAX_PDF_PAGES pages: a huge file found on
    the web must not tie up a scrape worker."""
    if PYMUPDF_AVAILABLE:
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                text = "\n".join(page.get_text() for page, _ in zip(doc, range(MAX_PDF_PAGES)))
            if text.strip():
                return text
        except Exception:
            pass
    if PDFMINER_AVAILABLE:
        try:
            text = pdfminer_extract(io.BytesIO(pdf_bytes), maxpages=MAX_PDF_PAGES)
            if text.strip():
                return text
        except Exception:
            pass
    return ""


def download_and_extract_pdf(pdf_url: str) -> str:
    if not pdf_url or not pdf_url.strip():
        return ""
    try:
        sess = _pdf_session()
        pdf_bytes = _fetch_pdf_bytes(sess, pdf_url, timeout=30)
        if not pdf_bytes:
            return ""

        return pdf_text(pdf_bytes)
    except Exception as e:
        logger.error(f"PDF download error: {e}")
        return ""
