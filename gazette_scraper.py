"""Selenium scraper for the eGazette listing and its PDF viewer (from RegulatoryFeed.py)."""

import io
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

import requests


try:
    from selenium.common.exceptions import (
        NoSuchElementException,
        TimeoutException,
    )
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


from gazette_pdf import (  # noqa: E402
    PDFMINER_AVAILABLE,
    PYMUPDF_AVAILABLE,
    _fetch_pdf_bytes,
    _pdf_session,
    _scrape_fast_mode,
    filter_hindi_text,
    fitz,
    guess_pdf_url,
    pdfminer_extract,
)

logger = logging.getLogger(__name__)


class GazetteScraper:
    def __init__(self, fast_mode: bool | None = None):
        self.driver = None
        self.fast_mode = _scrape_fast_mode() if fast_mode is None else fast_mode
        self.on_progress = None  # optional callback(phase, message)

    def setup_driver(self, headless=True):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not installed")
        import browser

        self.driver = browser.launch(headless=headless, hide_automation=True)
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
