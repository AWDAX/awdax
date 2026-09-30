"""
RegulatoryFeed – eGazette scraper, AI summarizer (Gemini), and background workers.
Uses local SQLite; imported by app.py as a service module.
"""

import hashlib
import io
import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any
from urllib.parse import urljoin

import sqlite3
import requests

try:
    import certifi
except ImportError:
    certifi = None  # type: ignore[assignment,misc]

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
    )
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import fitz  # PyMuPDF
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
# Database helper (local SQLite)
# ---------------------------------------------------------------------------

_DB_INITIALIZED = False
_DB_INIT_LOCK = threading.Lock()


def _db_path() -> str:
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "regulatory.sqlite")
    return os.getenv("SQLITE_PATH", default)


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gazettes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gazette_id TEXT NOT NULL UNIQUE,
            ministry TEXT,
            department TEXT,
            office TEXT,
            subject TEXT,
            part_section TEXT,
            issue_date TEXT,
            publish_date TEXT,
            pdf_url TEXT,
            pdf_text TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS gazette_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gazette_id INTEGER NOT NULL UNIQUE REFERENCES gazettes(id),
            topic TEXT,
            summary TEXT,
            key_highlights TEXT,
            legal_clauses TEXT,
            states TEXT,
            market_impact TEXT,
            industry_tags TEXT,
            importance TEXT DEFAULT 'medium',
            redline_analysis TEXT,
            redline_change_keywords TEXT,
            redline_impact_tags TEXT,
            redline_generated_at TEXT,
            clause_comparison TEXT,
            clause_comparison_generated_at TEXT,
            brief_summary TEXT,
            brief_summary_generated_at TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()


def _get_db() -> sqlite3.Connection:
    global _DB_INITIALIZED
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if not _DB_INITIALIZED:
        with _DB_INIT_LOCK:
            if not _DB_INITIALIZED:
                _init_db(conn)
                _DB_INITIALIZED = True
    return conn


def _as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


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
    if "egazette.gov.in" in (pdf_url or ""):
        verify_opts.append(False)
    last_err: Exception | None = None
    for verify in verify_opts:
        try:
            resp = sess.get(pdf_url, timeout=timeout, verify=verify)
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


def download_and_extract_pdf(pdf_url: str) -> str:
    if not pdf_url or not pdf_url.strip():
        return ""
    try:
        sess = _pdf_session()
        pdf_bytes = _fetch_pdf_bytes(sess, pdf_url, timeout=30)
        if not pdf_bytes:
            return ""

        if PYMUPDF_AVAILABLE:
            try:
                parts = []
                with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                    for page in doc:
                        parts.append(page.get_text())
                text = "\n".join(parts)
                if text.strip():
                    return text
            except Exception:
                pass

        if PDFMINER_AVAILABLE:
            try:
                text = pdfminer_extract(io.BytesIO(pdf_bytes))
                if text.strip():
                    return text
            except Exception:
                pass

        return ""
    except Exception as e:
        logger.error(f"PDF download error: {e}")
        return ""


# ---------------------------------------------------------------------------
# AI Summariser (Gemini)
# ---------------------------------------------------------------------------

class AISummarizer:
    def __init__(self):
        self.cache: dict[str, Any] = {}

    @staticmethod
    def _cache_key(text: str, subject: str) -> str:
        return hashlib.md5(f"{subject}:{text[:1000]}".encode()).hexdigest()

    # ── structured summary ──────────────────────────────────────────
    @staticmethod
    def _normalize_industry_tags(raw) -> list[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            raw = [raw]
        if not isinstance(raw, list):
            return []
        out = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
            if len(out) >= 12:
                break
        return out

    def generate_summary(self, text: str, subject: str, gazette_id: str = None) -> dict[str, Any]:
        if not text or not text.strip():
            return self._fallback(text or "", subject)
        ck = self._cache_key(text, subject)
        if ck in self.cache:
            return self.cache[ck]
        result = self._gemini_summary(text, subject)
        if result and self._validate(result):
            result["industry_tags"] = self._normalize_industry_tags(result.get("industry_tags"))
            self.cache[ck] = result
            return result
        fb = self._fallback(text, subject)
        self.cache[ck] = fb
        return fb

    def _gemini_summary(self, text: str, subject: str) -> dict | None:
        if not GEMINI_AVAILABLE:
            return None
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key.startswith("your_"):
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
            prompt = f"""Analyze this government gazette document and provide a structured summary.

Subject: {subject}
Document Text: {text[:4000]}

Provide ONLY a valid JSON response:
{{
    "topic": "Brief topic title",
    "summary": "2-3 sentence summary",
    "key_highlights": ["Key point 1", "Key point 2", "Key point 3"],
    "legal_clauses": ["Section/Act references"],
    "states": ["List of states mentioned"],
    "market_impact": "Brief market impact assessment",
    "industry_tags": ["2-8 short labels for industries/sectors this notification materially affects, e.g. Banking & finance, Pharmaceuticals, Energy & power, Manufacturing, IT & telecom, Agriculture, Real estate, Transport & logistics, Retail & e-commerce, Environment & waste, MSME, Defence, Education. Use Title Case. Omit generic tags like Government or Public sector unless that is the sole focus."]
}}"""
            resp = model.generate_content(prompt)
            m = re.search(r"\{.*\}", resp.text.strip(), re.DOTALL)
            return json.loads(m.group()) if m else None
        except Exception as e:
            logger.error(f"Gemini summary error: {e}")
            return None

    @staticmethod
    def _validate(s: dict) -> bool:
        return all(f in s for f in ("topic", "summary", "key_highlights", "legal_clauses", "states", "market_impact"))

    @staticmethod
    def _fallback(text: str, subject: str) -> dict[str, Any]:
        tl = (text or "").lower()
        clauses = re.findall(r"[Ss]ection\s+\d+[A-Za-z]*", text)[:5]
        clauses += re.findall(r"Act,?\s+\d{4}", text)[:3]
        states_set = {
            "andhra pradesh", "assam", "bihar", "chhattisgarh", "delhi",
            "goa", "gujarat", "haryana", "jharkhand", "karnataka", "kerala",
            "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
            "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
            "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
        }
        found_states = [s.title() for s in states_set if s in tl]
        highlights = []
        if "amendment" in tl:
            highlights.append("Regulatory amendment")
        if "notification" in tl:
            highlights.append("Government notification")
        mi = "Administrative notification"
        if any(k in tl for k in ("land acquisition", "railway", "infrastructure")):
            mi = "Potential infrastructure development impact"
        elif any(k in tl for k in ("amendment", "rules", "regulations")):
            mi = "Regulatory change impact"
        ind_tags: list[str] = []
        ind_kw = [
            ("pharma", "Healthcare & pharmaceuticals"),
            ("drug", "Healthcare & pharmaceuticals"),
            ("bank", "Banking & finance"),
            ("insurance", "Insurance"),
            ("tax", "Tax & compliance"),
            ("gst", "Tax & compliance"),
            ("energy", "Energy & power"),
            ("power", "Energy & power"),
            ("coal", "Mining & natural resources"),
            ("telecom", "IT & telecom"),
            ("railway", "Transport & logistics"),
            ("aviation", "Aviation"),
            ("environment", "Environment & sustainability"),
            ("waste", "Environment & sustainability"),
            ("agriculture", "Agriculture"),
            ("msme", "MSME"),
            ("defence", "Defence"),
            ("education", "Education"),
        ]
        for kw, label in ind_kw:
            if kw in tl and label not in ind_tags:
                ind_tags.append(label)
            if len(ind_tags) >= 6:
                break
        if not ind_tags:
            ind_tags = ["General regulatory"]
        return {
            "topic": (subject or "Government Notification")[:100],
            "summary": f"Government notification regarding {subject}.",
            "key_highlights": highlights or ["Government notification"],
            "legal_clauses": clauses,
            "states": found_states[:10],
            "market_impact": mi,
            "industry_tags": ind_tags,
        }

    # ── brief summary ───────────────────────────────────────────────
    def generate_brief_summary(self, pdf_text: str, subject: str) -> str | None:
        if not pdf_text or not GEMINI_AVAILABLE:
            return None
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key.startswith("your_"):
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
            trimmed = pdf_text[:10000]
            prompt = f"""You are a legal and business analyst. Summarize this gazette notification simply.

Subject: {subject}
Document Text:
{trimmed}

Your summary should:
- Explain the main purpose in simple terms
- Highlight what changes, rules, or permissions are introduced
- Mention who is affected
- List any actions required, deadlines, or benefits
- Avoid legal jargon
- Keep it short, crisp, business-focused

Use markdown: **bold** for key terms, bullet points for lists, ## for headings.
Return only the markdown-formatted summary text."""
            resp = model.generate_content(prompt)
            out = resp.text.strip()
            out = re.sub(r"```.*?```", "", out, flags=re.DOTALL).strip()
            return out or None
        except Exception as e:
            logger.error(f"Brief summary error: {e}")
            return None

    # ── redline analysis ────────────────────────────────────────────
    def generate_redline_analysis(
        self, subject: str, summary_text: str = "",
        key_highlights: list = None, legal_clauses: list = None,
        market_impact: str = "", states: list = None,
        pdf_text: str = None,
    ) -> dict[str, Any] | None:
        has_pdf = pdf_text and len(pdf_text.strip()) > 50
        has_summary = summary_text and summary_text.strip()
        if not has_pdf and not has_summary:
            return None
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not GEMINI_AVAILABLE:
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
            parts = [f"Subject: {subject}"]
            if has_summary:
                parts.append(f"Summary: {summary_text}")
            if key_highlights:
                parts.append(f"Key Highlights: {', '.join(key_highlights)}")
            if legal_clauses:
                parts.append(f"Legal Clauses: {', '.join(legal_clauses)}")
            if market_impact:
                parts.append(f"Metadata: {market_impact}")
            if states:
                parts.append(f"States: {', '.join(states)}")
            if has_pdf:
                parts.append(f"Full Document Text:\n{pdf_text[:10000]}")
            ctx = "\n\n".join(parts)
            prompt = f"""You are a legal analyst specializing in Indian government gazette notifications.
Analyze this notification and identify regulatory or policy changes.

{ctx}

Provide ONLY valid JSON:
{{
    "change_keywords": ["list of 3-5 short change tags, prefix + for additions, - for removals"],
    "impact_tags": ["2-4 tags for who/what is impacted"],
    "redline_analysis": "Markdown explanation (3-5 paragraphs): (1) previous rule, (2) what changed, (3) who is affected, (4) deadlines/actions. Use **bold** for key terms."
}}

IMPORTANT: Always produce meaningful analysis. Never say content is unavailable."""
            resp = model.generate_content(prompt)
            m = re.search(r"\{.*\}", resp.text.strip(), re.DOTALL)
            if m:
                data = json.loads(m.group())
                bad = ["not available", "not possible", "cannot be determined", "no document"]
                if any(p in (data.get("redline_analysis", "")).lower() for p in bad):
                    return None
                if "change_keywords" in data and "impact_tags" in data and "redline_analysis" in data:
                    return data
            return None
        except Exception as e:
            logger.error(f"Redline error: {e}")
            return None

    # ── clause-by-clause comparison ─────────────────────────────────
    def generate_clause_comparison(self, pdf_text: str, subject: str) -> list | None:
        if not pdf_text or len(pdf_text.strip()) < 50:
            return None
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not GEMINI_AVAILABLE:
            return None
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-3.1-flash-lite-preview")
            trimmed = pdf_text[:12000]
            prompt = f"""You are a legal analyst specializing in Indian government gazette notifications.

Subject: {subject}

Full gazette text:
{trimmed}

Extract EVERY clause-level change. For each change identify:
1. Clause/section/rule reference
2. OLD provision (before notification)
3. NEW provision (after notification)
4. Type of change

Return ONLY a valid JSON array:
[
  {{
    "clause_ref": "Section/Rule reference",
    "old_text": "Previous provision in plain English",
    "new_text": "New provision in plain English",
    "change_type": "added | amended | substituted | omitted | replaced"
  }}
]

Rules:
- Extract ALL identifiable changes
- Write in plain English for a business audience
- Return empty array [] only if genuinely no clause changes
- No markdown code blocks, raw JSON only"""
            resp = model.generate_content(prompt)
            result = resp.text.strip()
            if result.startswith("```"):
                result = re.sub(r"^```(?:json)?\s*", "", result)
                result = re.sub(r"\s*```$", "", result)
            data = json.loads(result)
            if isinstance(data, list):
                valid = [c for c in data if isinstance(c, dict) and "clause_ref" in c]
                return valid or None
            return None
        except Exception as e:
            logger.error(f"Clause comparison error: {e}")
            return None


# ---------------------------------------------------------------------------
# eGazette Web Scraper (Selenium)
# ---------------------------------------------------------------------------

class GazetteScraper:
    def __init__(self, fast_mode: bool | None = None):
        self.driver = None
        self.fast_mode = _scrape_fast_mode() if fast_mode is None else fast_mode
        self.on_progress = None  # optional callback(phase, message)

    def setup_driver(self, headless=True):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not installed")
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return self.driver

    def handle_popups(self) -> bool:
        try:
            for sel in ["input[name='ImgMessage_OK']", "#ImgMessage_OK", "input[src*='OK.png']"]:
                try:
                    btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    btn.click()
                    time.sleep(2)
                    break
                except TimeoutException:
                    continue
            for sel in ["a.cancel img[src*='Cross.png']", "a.cancel", "img[src*='Cross.png']"]:
                try:
                    el = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                    )
                    el.click()
                    time.sleep(2)
                    break
                except TimeoutException:
                    continue

            # Move into full paginated listing (critical; homepage widgets show only few rows)
            view_all_candidates = [
                "//a[contains(normalize-space(text()), 'View All')]",
                "//a[contains(@href, 'Gazette.aspx')]",
            ]
            for xp in view_all_candidates:
                try:
                    link = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, xp))
                    )
                    self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
                    link.click()
                    time.sleep(3)
                    return True
                except TimeoutException:
                    continue
            logger.warning("View All link not found; scraper may see only homepage subset")
            return True
        except Exception as e:
            logger.error(f"Popup handling error: {e}")
            return False

    def get_pagination_info(self) -> int:
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            page_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'Page$')]")
            if not page_links:
                return 1
            nums = []
            for link in page_links:
                href = link.get_attribute("href") or ""
                m = re.search(r"Page\$(\d+)", href)
                if m:
                    nums.append(int(m.group(1)))
            return max(nums) if nums else 1
        except Exception:
            return 1

    def navigate_to_page(self, page_num: int) -> bool:
        try:
            if page_num == 1:
                return True
            page_link = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f"//a[contains(@href, 'Page${page_num}')]"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", page_link)
            page_link.click()
            time.sleep(3)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            return True
        except Exception:
            return False

    def _get_pdf_url_from_viewer(self) -> str | None:
        try:
            for sel in ("embed", "object", "iframe"):
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    orig = el.get_attribute("original-url")
                    if orig:
                        return orig
                    src = el.get_attribute("src") or el.get_attribute("data")
                    if src and ".pdf" in src.lower():
                        return urljoin(self.driver.current_url, src)
            html = self.driver.page_source or ""
            m = re.search(r'original-url\s*=\s*"([^"]+)"', html, re.IGNORECASE)
            if m:
                return m.group(1)
            m = re.search(r'src\s*=\s*"([^"]+?\.pdf[^"]*)"', html, re.IGNORECASE)
            if m:
                return urljoin(self.driver.current_url, m.group(1))
            return None
        except Exception:
            return None

    def _create_requests_session(self):
        try:
            sess = requests.Session()
            for c in self.driver.get_cookies():
                sess.cookies.set(c["name"], c["value"], domain=c.get("domain"), path=c.get("path", "/"))
            return sess
        except Exception:
            return None

    def _extract_pdf_text_from_viewer(self) -> tuple:
        """Returns (pdf_url, pdf_text)"""
        try:
            try:
                WebDriverWait(self.driver, 6).until(
                    lambda d: len(d.find_elements(By.CSS_SELECTOR, "embed,object,iframe")) > 0
                )
            except Exception:
                pass
            pdf_url = self._get_pdf_url_from_viewer() or ""
            if pdf_url:
                sess = self._create_requests_session()
                if sess:
                    try:
                        content = _fetch_pdf_bytes(_pdf_session(sess), pdf_url, timeout=25)
                        if content:
                            if PYMUPDF_AVAILABLE:
                                try:
                                    parts = []
                                    with fitz.open(stream=content, filetype="pdf") as doc:
                                        for p in doc:
                                            parts.append(p.get_text())
                                    text = "\n".join(parts)
                                    if text.strip():
                                        return pdf_url, text
                                except Exception:
                                    pass
                            if PDFMINER_AVAILABLE:
                                text = pdfminer_extract(io.BytesIO(content))
                                if text.strip():
                                    return pdf_url, text
                    except Exception:
                        pass
            return pdf_url, ""
        except Exception:
            return "", ""

    def _click_download_and_extract(self, row_el) -> tuple:
        """Click download on a row. Returns (pdf_url, pdf_text)."""
        download_selector = (
            "input[type='image'][id*='imgbtndownload'], "
            "input[type='image'][name*='imgbtndownload'], "
            "input[type='image'][id*='ImgDownLoad'], "
            "input[type='image'][name*='ImgDownLoad'], "
            "input[type='image'][id*='download'], "
            "input[type='image'][name*='download']"
        )
        try:
            btn = row_el.find_element(
                By.CSS_SELECTOR,
                download_selector,
            )
        except NoSuchElementException:
            return "", ""
        orig_win = self.driver.current_window_handle
        wins_before = set(self.driver.window_handles)
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            btn.click()
        except Exception:
            return "", ""
        try:
            WebDriverWait(self.driver, 8).until(
                lambda d: len(d.window_handles) > len(wins_before) or "ViewPDF" in (d.current_url or "")
            )
        except Exception:
            pass
        new_wins = list(set(self.driver.window_handles) - wins_before)
        opened_tab = False
        if new_wins:
            self.driver.switch_to.window(new_wins[0])
            opened_tab = True
        else:
            try:
                WebDriverWait(self.driver, 10).until(EC.url_contains("ViewPDF"))
            except Exception:
                pass
        pdf_url, raw_text = self._extract_pdf_text_from_viewer()
        pdf_text = filter_hindi_text(raw_text) if raw_text else ""
        try:
            if opened_tab:
                self.driver.close()
                self.driver.switch_to.window(orig_win)
            else:
                self.driver.back()
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
        except Exception:
            try:
                self.driver.switch_to.window(orig_win)
            except Exception:
                pass
        return pdf_url or "", pdf_text or ""

    def scrape_page_data(self, page_num: int, check_exists=None):
        """Scrape one page. Returns (row_dicts, should_stop)."""
        logger.info(f"Scraping page {page_num}...")
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
        except TimeoutException:
            logger.warning("Timed out waiting for page table")
            return [], False

        page_rows: list[dict[str, Any]] = []
        should_stop = False
        # Use reference behavior: target main table id in full listing.
        try:
            main_table = self.driver.find_element(By.ID, "gvGazetteList")
        except NoSuchElementException:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            main_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr"))) if tables else None
        if not main_table:
            logger.warning("Main gazette list table not found")
            return [], False

        rows = main_table.find_elements(By.TAG_NAME, "tr")
        headers = []
        gazette_id_col = None
        for row in rows:
            ths = row.find_elements(By.TAG_NAME, "th")
            if ths:
                headers = [c.text.strip() for c in ths]
                for i, h in enumerate(headers):
                    if "gazette" in h.lower() and "id" in h.lower():
                        gazette_id_col = i
                        break
                break

        # Fallback fixed header order for current egazette grid.
        if not headers:
            headers = ["Ministry / Organization", "Subject", "Issue Date", "Publish Date", "Gazette ID", "Download"]
            gazette_id_col = 4

        total_rows = len(rows)
        for row_index in range(total_rows):
            try:
                # Reacquire to avoid stale refs after opening/closing PDF tabs.
                try:
                    main_table = self.driver.find_element(By.ID, "gvGazetteList")
                except NoSuchElementException:
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    if not tables:
                        break
                    main_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                fresh_rows = main_table.find_elements(By.TAG_NAME, "tr")
                if row_index >= len(fresh_rows):
                    break
                row = fresh_rows[row_index]

                if row.find_elements(By.TAG_NAME, "th"):
                    continue
                cells = row.find_elements(By.TAG_NAME, "td")
                if not cells:
                    continue
                values = [c.text.strip() for c in cells]
                if not any(values):
                    continue
                if len(values) < 5:
                    continue

                gazette_id = ""
                if gazette_id_col is not None and gazette_id_col < len(values):
                    gazette_id = values[gazette_id_col]
                if not gazette_id:
                    for v in values:
                        if re.match(r"^[A-Z0-9/-]{6,}$", v):
                            gazette_id = v
                            break
                if not gazette_id:
                    continue

                if check_exists and check_exists(gazette_id):
                    logger.info(f"Found existing gazette {gazette_id}; stopping page scan")
                    should_stop = True
                    break

                if self.fast_mode:
                    pdf_url = guess_pdf_url(gazette_id)
                    pdf_text = ""
                else:
                    pdf_url, pdf_text = self._click_download_and_extract(row)

                row_dict: dict[str, Any] = {}
                for i, h in enumerate(headers):
                    row_dict[h] = values[i] if i < len(values) else ""
                row_dict["Gazette ID"] = gazette_id
                row_dict["PDF_URL"] = pdf_url
                row_dict["PDF_Text"] = pdf_text
                page_rows.append(row_dict)
                if self.on_progress:
                    self.on_progress("row", gazette_id)
                time.sleep(0.15 if self.fast_mode else 0.4)
            except Exception as e:
                logger.warning(f"Skipping row due to parse error: {e}")
                continue

        logger.info(f"Extracted {len(page_rows)} rows from page {page_num}")
        return page_rows, should_stop

    def scrape_all(self, max_pages=3, check_exists=None, on_row=None) -> int:
        """Full scrape. If on_row is provided, process each row immediately."""
        logger.info("Starting eGazette scrape...")
        self.setup_driver(headless=True)
        processed = 0
        try:
            self.driver.get("https://egazette.gov.in")
            time.sleep(2 if self.fast_mode else 3)
            if not self.handle_popups():
                raise RuntimeError(
                    "Could not open eGazette listing (popups or navigation failed)."
                )
            total = min(self.get_pagination_info(), max_pages)
            for p in range(1, total + 1):
                if p > 1 and not self.navigate_to_page(p):
                    continue
                page_data, stop = self.scrape_page_data(p, check_exists)
                for row in page_data:
                    if on_row:
                        try:
                            on_row(row)
                        except Exception as e:
                            logger.error(f"on_row processing error: {e}")
                            continue
                    processed += 1
                if stop:
                    break
                time.sleep(0.5 if self.fast_mode else 2)
        except Exception as e:
            logger.error(f"Scrape error: {e}")
        finally:
            if self.driver:
                self.driver.quit()

        return processed


# ---------------------------------------------------------------------------
# Scraping + processing service
# ---------------------------------------------------------------------------

class RegulatoryFeedService:
    def __init__(self):
        self.is_running = False
        self._scrape_loop_running = False
        self._scrape_lock = threading.Lock()
        self._workers_started = False
        self.ai = AISummarizer()
        self._importance_weight = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        self.scrape_status: dict[str, Any] = {
            "phase": "idle",
            "message": "Ready. Click Start scrape to fetch eGazette notifications.",
            "last_error": None,
            "rows_this_run": 0,
            "gazette_count": 0,
            "started_at": None,
            "finished_at": None,
        }
        self._event_subscribers: list[queue.Queue] = []
        self._event_lock = threading.Lock()
        self._summary_queue: queue.Queue[int | None] = queue.Queue()

    def subscribe_events(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._event_lock:
            self._event_subscribers.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue) -> None:
        with self._event_lock:
            if q in self._event_subscribers:
                self._event_subscribers.remove(q)

    def emit_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"type": event_type, "ts": time.time()}
        if data:
            payload.update(data)
        with self._event_lock:
            for sub in list(self._event_subscribers):
                try:
                    sub.put_nowait(payload)
                except queue.Full:
                    try:
                        sub.get_nowait()
                        sub.put_nowait(payload)
                    except queue.Empty:
                        pass

    def _set_status(self, **kwargs: Any) -> None:
        self.scrape_status.update(kwargs)
        self.scrape_status["gazette_count"] = self._gazette_count()
        self.emit_event("status", self.get_scrape_status())

    def get_scrape_status(self) -> dict[str, Any]:
        self.scrape_status["gazette_count"] = self._gazette_count()
        self.scrape_status["is_running"] = self.is_running
        self.scrape_status["loop_running"] = self._scrape_loop_running
        return dict(self.scrape_status)

    def trigger_scrape(self, max_pages: int = 3) -> dict[str, Any]:
        with self._scrape_lock:
            if self.is_running:
                return {
                    "started": False,
                    "reason": "already_running",
                    **self.get_scrape_status(),
                }
            if not self._workers_started:
                self.start_background_workers()
                self._workers_started = True
            t = threading.Thread(
                target=self._run_scrape_cycle,
                args=(max_pages,),
                daemon=True,
                name="scrape-cycle",
            )
            t.start()
            return {"started": True, **self.get_scrape_status()}

    def _run_scrape_cycle(self, max_pages: int = 3) -> None:
        self.is_running = True
        self._set_status(
            phase="starting",
            message="Launching browser and opening eGazette…",
            last_error=None,
            rows_this_run=0,
            started_at=time.time(),
            finished_at=None,
        )
        self.emit_event("log", {"level": "info", "message": "Scrape cycle started"})
        try:
            if not SELENIUM_AVAILABLE:
                raise RuntimeError(
                    "Selenium is not installed. Run: pip install selenium"
                )
            current_total = self._gazette_count()
            stop_on_existing = current_total >= self.BOOTSTRAP_TARGET
            fast = _scrape_fast_mode()
            mode = "fast (list + background PDF/AI)" if fast else "full (browser PDF)"
            self._set_status(
                phase="scraping",
                message=f"Scraping up to {max_pages} page(s) — {mode}…",
            )
            scraper = GazetteScraper(fast_mode=fast)
            scraper.on_progress = lambda phase, msg: self.emit_event(
                "log", {"level": "info", "message": f"Listing row {msg}"}
            )
            processed = scraper.scrape_all(
                max_pages=max_pages,
                check_exists=self.gazette_exists if stop_on_existing else None,
                on_row=self._process_scraped_row,
            )
            saved = int(self.scrape_status.get("rows_this_run") or 0)
            self.scrape_status["gazette_count"] = self._gazette_count()
            if processed == 0 and saved == 0:
                self._set_status(
                    phase="idle",
                    message=(
                        "Scrape finished but no rows were saved. "
                        "Check Chrome/ChromeDriver and terminal logs."
                    ),
                )
            else:
                self._set_status(
                    phase="idle",
                    message=(
                        f"Listing done — {saved} saved ({processed} scraped). "
                        "Summaries still processing in background."
                    ),
                )
            self.emit_event("log", {"level": "info", "message": self.scrape_status["message"]})
            logger.info(
                "Scrape cycle done. scraped=%s saved=%s total=%s",
                processed,
                saved,
                self.scrape_status["gazette_count"],
            )
        except Exception as e:
            logger.error("Scrape cycle error: %s", e)
            self._set_status(
                phase="error",
                last_error=str(e),
                message=f"Scrape failed: {e}",
            )
            self.emit_event("log", {"level": "error", "message": str(e)})
        finally:
            self.is_running = False
            self.scrape_status["finished_at"] = time.time()
            self.scrape_status["gazette_count"] = self._gazette_count()
            self.emit_event("status", self.get_scrape_status())

    @staticmethod
    def _wrap_industry_tags(tags: list) -> list:
        if not tags:
            return []
        uniq = []
        seen = set()
        for t in tags:
            name = str(t or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(name)
        if not uniq:
            return []
        weight = round(1.0 / len(uniq), 4)
        return [{"industry": u, "weight": weight} for u in uniq]

    @staticmethod
    def _compute_importance(g: dict, s: dict) -> str:
        score = 0
        txt = " ".join([
            str(g.get("subject") or ""),
            str(g.get("pdf_text") or "")[:4000],
            str(s.get("summary") or ""),
            str(s.get("market_impact") or ""),
        ]).lower()

        keywords_critical = ["penalty", "fine", "ban", "prohibit", "recall", "cease", "shutdown"]
        keywords_high = ["mandatory", "compliance", "deadline", "last date", "must", "require", "obligatory"]
        for kw in keywords_critical:
            if kw in txt:
                score += 2
        for kw in keywords_high:
            if kw in txt:
                score += 1

        if s.get("legal_clauses"):
            score += 1
        if s.get("states"):
            score += 1
        mi = (s.get("market_impact") or "").lower()
        if any(k in mi for k in ["significant", "major", "high", "serious"]):
            score += 2
        elif any(k in mi for k in ["moderate", "medium"]):
            score += 1

        pdf_len = len((g.get("pdf_text") or "").strip())
        if pdf_len > 5000:
            score += 2
        elif pdf_len > 1500:
            score += 1

        if score >= 5:
            return "critical"
        if score >= 3:
            return "high"
        if score >= 1:
            return "medium"
        return "low"

    # ── check existence in DB ──────────────────────────────────────
    @staticmethod
    def gazette_exists(gazette_id: str) -> bool:
        try:
            conn = _get_db()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM gazettes WHERE gazette_id = ?", (gazette_id,))
            exists = cur.fetchone() is not None
            cur.close()
            conn.close()
            return exists
        except Exception:
            return False

    # ── store / update gazette + summary ────────────────────────────
    def _store_gazette(self, row: dict) -> int | None:
        def pick(*names, default=""):
            for n in names:
                if n in row and row.get(n) not in (None, ""):
                    return row.get(n)
            return default

        gazette_id = pick("Gazette ID", "GazetteId", "Gazette No", "Gazette Number", default="")
        if not gazette_id:
            # Fallback: scan row values for likely gazette id pattern.
            for v in row.values():
                txt = str(v or "").strip()
                if re.match(r"^[A-Z0-9/-]{6,}$", txt):
                    gazette_id = txt
                    break
        if not gazette_id:
            return None
        pdf_text = pick("PDF_Text", default="") or ""
        pdf_url = pick("PDF_URL", default="") or ""
        if not pdf_url and gazette_id:
            pdf_url = guess_pdf_url(gazette_id)
        if (
            len(pdf_text.strip()) < 50
            and pdf_url
            and not _scrape_fast_mode()
        ):
            pdf_text = download_and_extract_pdf(pdf_url)
        if pdf_text:
            pdf_text = filter_hindi_text(pdf_text)

        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT id, pdf_text FROM gazettes WHERE gazette_id = ?", (gazette_id,))
            existing = cur.fetchone()
            if existing:
                g_id = existing["id"]
                old_len = len((existing["pdf_text"] or "").strip())
                if pdf_text and len(pdf_text.strip()) > old_len:
                    cur.execute(
                        "UPDATE gazettes SET pdf_text=?, pdf_url=?, updated_at=datetime('now') WHERE id=?",
                        (pdf_text, pdf_url, g_id),
                    )
                    conn.commit()
                return g_id
            else:
                cur.execute(
                    """INSERT INTO gazettes
                       (gazette_id, ministry, department, office, subject,
                        part_section, issue_date, publish_date, pdf_url, pdf_text)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        gazette_id,
                        pick("Ministry / Organization", "Ministry", default=""),
                        pick("Department", default=""),
                        pick("Office", default=""),
                        pick("Subject", default=""),
                        pick("Part & Section", "Part Section", default=""),
                        pick("Issue Date", default=""),
                        pick("Publish Date", default=""),
                        pdf_url,
                        pdf_text,
                    ),
                )
                g_id = cur.lastrowid
                conn.commit()
                return g_id
        except Exception as e:
            logger.error(f"Store gazette error: {e}")
            return None
        finally:
            cur.close()
            conn.close()

    def _ensure_pdf_text(self, g_id: int) -> None:
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT pdf_text, pdf_url, gazette_id FROM gazettes WHERE id=?", (g_id,))
            row = _as_dict(cur.fetchone())
            if not row:
                return
            pdf_text = (row.get("pdf_text") or "").strip()
            pdf_url = row.get("pdf_url") or guess_pdf_url(row.get("gazette_id") or "")
            if len(pdf_text) >= 50:
                return
            if not pdf_url:
                return
            fetched = download_and_extract_pdf(pdf_url)
            if not fetched:
                return
            fetched = filter_hindi_text(fetched)
            cur.execute(
                "UPDATE gazettes SET pdf_text=?, pdf_url=?, updated_at=datetime('now') WHERE id=?",
                (fetched, pdf_url, g_id),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

    def _generate_summary_for(self, g_id: int):
        self._ensure_pdf_text(g_id)
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM gazettes WHERE id=?", (g_id,))
            g = _as_dict(cur.fetchone())
            if not g:
                return
            has_pdf = bool(g.get("pdf_text") and len((g.get("pdf_text") or "").strip()) >= 50)
            subject = g.get("subject") or "Government Notification"
            if has_pdf:
                s = self.ai.generate_summary(g["pdf_text"], subject, g["gazette_id"])
            else:
                # Fast fallback tagging when PDF text is not available yet.
                quick_text = " ".join(
                    [
                        str(g.get("subject") or ""),
                        str(g.get("ministry") or ""),
                        str(g.get("department") or ""),
                        str(g.get("office") or ""),
                    ]
                ).strip()
                s = self.ai._fallback(quick_text, subject)
            importance = self._compute_importance(g, s)
            industry_payload = self._wrap_industry_tags(s.get("industry_tags", []))
            cur.execute(
                """INSERT INTO gazette_summaries
                   (gazette_id, topic, summary, key_highlights, legal_clauses, states, market_impact, industry_tags, importance)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT (gazette_id) DO UPDATE SET
                       industry_tags = CASE
                           WHEN gazette_summaries.industry_tags IS NULL
                                OR gazette_summaries.industry_tags = '[]'
                           THEN excluded.industry_tags
                           ELSE gazette_summaries.industry_tags
                       END,
                       importance = CASE
                           WHEN gazette_summaries.importance IS NULL
                                OR gazette_summaries.importance = 'medium'
                           THEN excluded.importance
                           ELSE gazette_summaries.importance
                       END,
                       updated_at = datetime('now')""",
                (
                    g_id, s.get("topic"), s.get("summary"),
                    json.dumps(s.get("key_highlights", [])),
                    json.dumps(s.get("legal_clauses", [])),
                    json.dumps(s.get("states", [])),
                    s.get("market_impact"),
                    json.dumps(industry_payload),
                    importance,
                ),
            )
            conn.commit()
            sid = cur.lastrowid
            if sid:
                logger.info(f"Summary saved for gazette {g['gazette_id']} (summary id {sid})")
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
        finally:
            cur.close()
            conn.close()

    # ── continuous scrape loop ────────────────────────────────────────
    SCRAPE_INTERVAL = 3600  # seconds between scrape cycles (1 hour)
    BOOTSTRAP_TARGET = 100  # keep backfilling history until at least this many notifications

    def start_scraping(self, max_pages=20):
        """Start hourly background loop (first cycle runs immediately)."""
        if self._scrape_loop_running:
            return
        self._scrape_loop_running = True
        if not self._workers_started:
            self.start_background_workers()
            self._workers_started = True
        t = threading.Thread(
            target=self._scrape_loop,
            args=(max_pages,),
            daemon=True,
            name="scrape-loop",
        )
        t.start()

    def _scrape_loop(self, max_pages=3):
        while True:
            self._run_scrape_cycle(max_pages)
            self.scrape_status["phase"] = "sleeping"
            self.scrape_status["message"] = (
                f"Waiting {self.SCRAPE_INTERVAL // 60} min until next automatic scrape…"
            )
            time.sleep(self.SCRAPE_INTERVAL)

    def _process_scraped_row(self, row: dict[str, Any]):
        """Persist each scraped row; queue AI summary in background."""
        gid = row.get("Gazette ID") or row.get("GazetteId") or "unknown"
        self._set_status(phase="processing", message=f"Saving {gid}…")
        g_id = self._store_gazette(row)
        if g_id:
            self.scrape_status["rows_this_run"] = int(self.scrape_status.get("rows_this_run") or 0) + 1
            item = self.get_feed_item(g_id)
            if item:
                self.emit_event("item", {"item": item})
            self._summary_queue.put(g_id)
            self._set_status(
                message=(
                    f"Saved {self.scrape_status['rows_this_run']} this run "
                    f"({self.scrape_status['gazette_count']} total) — latest {gid}"
                ),
            )
            self.emit_event("log", {"level": "info", "message": f"Queued summary for {gid}"})

    @staticmethod
    def _gazette_count() -> int:
        try:
            conn = _get_db()
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM gazettes")
            n = cur.fetchone()[0]
            cur.close()
            conn.close()
            return int(n)
        except Exception:
            return 0

    # ── background workers ──────────────────────────────────────────
    def start_background_workers(self):
        threading.Thread(target=self._summary_worker, daemon=True, name="summary-worker").start()
        threading.Thread(target=self._redline_worker, daemon=True).start()
        # Brief + clause comparison are generated on-demand via tab click.

    def _summary_worker(self) -> None:
        while True:
            try:
                g_id = self._summary_queue.get(timeout=2)
            except queue.Empty:
                continue
            if g_id is None:
                break
            gid = "?"
            try:
                self._set_status(phase="summarizing", message=f"AI summary for gazette #{g_id}…")
                self._generate_summary_for(g_id)
                item = self.get_feed_item(g_id)
                if item:
                    gid = item.get("gazette_id") or gid
                    self.emit_event("item", {"item": item, "update": True})
                self.emit_event("log", {"level": "info", "message": f"Summary ready: {gid}"})
            except Exception as e:
                logger.error("Summary worker error for %s: %s", g_id, e)
                self.emit_event("log", {"level": "error", "message": f"Summary failed {gid}: {e}"})
            finally:
                self._summary_queue.task_done()
                if not self.is_running and self._summary_queue.empty():
                    self._set_status(phase="idle", message="All queued summaries processed.")

    def _redline_worker(self):
        time.sleep(60)
        while True:
            try:
                conn = _get_db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT s.id, s.summary, s.key_highlights, s.legal_clauses, s.states,
                           s.market_impact, s.redline_analysis, g.subject, g.pdf_text, g.gazette_id
                    FROM gazette_summaries s JOIN gazettes g ON s.gazette_id = g.id
                    WHERE (s.redline_analysis IS NULL OR s.redline_analysis = '')
                      AND g.pdf_text IS NOT NULL AND length(g.pdf_text) > 50
                    ORDER BY s.created_at DESC LIMIT 10
                """)
                rows = [_as_dict(r) for r in cur.fetchall()]
                cur.close()
                conn.close()
                for row in rows:
                    self._generate_redline_for_row(row)
                    time.sleep(35)
            except Exception as e:
                logger.error(f"Redline worker error: {e}")
            time.sleep(600)

    def _generate_redline_for_row(self, row: dict):
        try:
            result = self.ai.generate_redline_analysis(
                subject=row["subject"] or "Notification",
                summary_text=row.get("summary", ""),
                key_highlights=json.loads(row["key_highlights"]) if row.get("key_highlights") else [],
                legal_clauses=json.loads(row["legal_clauses"]) if row.get("legal_clauses") else [],
                market_impact=row.get("market_impact", ""),
                states=json.loads(row["states"]) if row.get("states") else [],
                pdf_text=row.get("pdf_text"),
            )
            if result:
                conn = _get_db()
                cur = conn.cursor()
                cur.execute(
                    """UPDATE gazette_summaries SET
                       redline_analysis=?, redline_change_keywords=?,
                       redline_impact_tags=?, redline_generated_at=datetime('now'), updated_at=datetime('now')
                       WHERE id=?""",
                    (
                        result.get("redline_analysis", ""),
                        json.dumps(result.get("change_keywords", [])),
                        json.dumps(result.get("impact_tags", [])),
                        row["id"],
                    ),
                )
                conn.commit()
                cur.close()
                conn.close()
                logger.info(f"Redline saved for summary {row['id']}")
        except Exception as e:
            logger.error(f"Redline gen error for {row['id']}: {e}")

    def _clause_worker(self):
        time.sleep(120)
        while True:
            try:
                conn = _get_db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT s.id, g.pdf_text, g.subject, g.gazette_id
                    FROM gazette_summaries s JOIN gazettes g ON s.gazette_id = g.id
                    WHERE (s.clause_comparison IS NULL OR s.clause_comparison = '' OR s.clause_comparison = '[]')
                      AND g.pdf_text IS NOT NULL AND length(g.pdf_text) > 50
                    ORDER BY s.created_at DESC LIMIT 10
                """)
                rows = [_as_dict(r) for r in cur.fetchall()]
                cur.close()
                conn.close()
                for row in rows:
                    try:
                        result = self.ai.generate_clause_comparison(row["pdf_text"], row["subject"] or "Notification")
                        conn2 = _get_db()
                        cur2 = conn2.cursor()
                        cur2.execute(
                            """UPDATE gazette_summaries SET
                               clause_comparison=?, clause_comparison_generated_at=datetime('now'), updated_at=datetime('now')
                               WHERE id=?""",
                            (json.dumps(result) if result else "[]", row["id"]),
                        )
                        conn2.commit()
                        cur2.close()
                        conn2.close()
                        if result:
                            logger.info(f"Clause comparison saved for summary {row['id']} ({len(result)} clauses)")
                    except Exception as e:
                        logger.error(f"Clause comparison error for {row['id']}: {e}")
                    time.sleep(30)
            except Exception as e:
                logger.error(f"Clause worker error: {e}")
            time.sleep(600)

    def _brief_worker(self):
        time.sleep(90)
        while True:
            try:
                conn = _get_db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT s.id, g.pdf_text, g.subject
                    FROM gazette_summaries s JOIN gazettes g ON s.gazette_id = g.id
                    WHERE (s.brief_summary IS NULL OR s.brief_summary = '')
                      AND g.pdf_text IS NOT NULL AND length(g.pdf_text) > 50
                    ORDER BY s.created_at DESC LIMIT 10
                """)
                rows = [_as_dict(r) for r in cur.fetchall()]
                cur.close()
                conn.close()
                for row in rows:
                    try:
                        brief = self.ai.generate_brief_summary(row["pdf_text"], row["subject"] or "Notification")
                        if brief:
                            conn2 = _get_db()
                            cur2 = conn2.cursor()
                            cur2.execute(
                                """UPDATE gazette_summaries SET
                                   brief_summary=?, brief_summary_generated_at=datetime('now'), updated_at=datetime('now')
                                   WHERE id=?""",
                                (brief, row["id"]),
                            )
                            conn2.commit()
                            cur2.close()
                            conn2.close()
                            logger.info(f"Brief summary saved for summary {row['id']}")
                    except Exception as e:
                        logger.error(f"Brief summary error for {row['id']}: {e}")
                    time.sleep(25)
            except Exception as e:
                logger.error(f"Brief worker error: {e}")
            time.sleep(600)

    def get_feed_item(self, g_id: int) -> dict[str, Any] | None:
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    g.id,
                    g.gazette_id,
                    g.ministry,
                    g.subject,
                    g.issue_date,
                    g.publish_date,
                    g.pdf_url,
                    s.topic,
                    s.summary,
                    s.importance,
                    s.market_impact,
                    s.created_at AS summary_created_at
                FROM gazettes g
                LEFT JOIN gazette_summaries s ON s.gazette_id = g.id
                WHERE g.id = ?
                """,
                (g_id,),
            )
            row = _as_dict(cur.fetchone())
            if not row:
                return None
            for key, val in row.items():
                if hasattr(val, "isoformat"):
                    row[key] = val.isoformat()
            return row
        finally:
            cur.close()
            conn.close()

    def list_feed(self, limit: int = 50) -> list[dict[str, Any]]:
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    g.id,
                    g.gazette_id,
                    g.ministry,
                    g.subject,
                    g.issue_date,
                    g.publish_date,
                    g.pdf_url,
                    s.topic,
                    s.summary,
                    s.importance,
                    s.market_impact,
                    s.created_at AS summary_created_at
                FROM gazettes g
                LEFT JOIN gazette_summaries s ON s.gazette_id = g.id
                ORDER BY g.id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            out: list[dict[str, Any]] = []
            for row in rows:
                item = _as_dict(row) or {}
                for key, val in item.items():
                    if hasattr(val, "isoformat"):
                        item[key] = val.isoformat()
                out.append(item)
            return out
        finally:
            cur.close()
            conn.close()


# Singleton
feed_service = RegulatoryFeedService()
