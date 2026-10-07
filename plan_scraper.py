"""Selenium engine for one planned listing: entry page, ready steps, pagination and table rows (from scraper.py)."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable

from inspector import ScrapePlan, load_page, page_load_seconds
from reasoning import ScrapeIntent
from url_guard import UnresolvableHost, UnsafeURL, check_url

logger = logging.getLogger(__name__)

try:
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


from gazette_pdf import guess_pdf_url  # noqa: E402


def guard_detail_url(url: str) -> str:
    """A detail/PDF URL built from an LLM-written template: dropped (empty) when it points somewhere not allowed."""
    if not url:
        return ""
    try:
        check_url(url)
    except UnresolvableHost:
        pass  # same as before: the download will simply fail
    except UnsafeURL:
        logger.warning("Dropped a detail URL that is not allowed")
        return ""
    return url


def fill_url_template(template: str, row: dict[str, Any], id_field: str) -> str:
    ext_id = str(row.get(id_field) or row.get("Gazette ID") or "")
    num_m = re.search(r"-(\d+)\s*$", ext_id)
    num = num_m.group(1) if num_m else ""
    year = str(time.gmtime().tm_year)
    date_m = re.search(r"-(\d{8})-\d+$", ext_id)
    if date_m:
        year = date_m.group(1)[4:8]
    try:
        return template.format(year=year, num=num, id=ext_id)
    except (KeyError, IndexError, ValueError, AttributeError):
        # The template was written by the model: braces it invented ({slug}, {0}, a stray "}") must cost this one link, not the page.
        logger.warning("Detail URL template could not be filled: %r", template[:120])
        return ""


class PlanDrivenScraper:
    def __init__(self, plan: ScrapePlan, fast_mode: bool = True, intent: ScrapeIntent | None = None):
        self.plan = plan
        self.fast_mode = fast_mode
        self.intent = intent
        self.driver = None
        self.on_progress: Callable[[str, str], None] | None = None
        self._headers_mapped = bool(plan.column_map)

    def setup_driver(self, headless: bool = True):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not installed")
        import browser

        self.driver = browser.launch(headless=headless)
        self.driver.set_page_load_timeout(page_load_seconds())
        return self.driver

    def quit(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None

    def run_ready_steps(self):
        for step in self.plan.listing_ready_steps:
            if not isinstance(step, dict):
                continue
            action = step.get("action", "click")
            if action != "click" or not str(step.get("selector") or "").strip():
                continue  # the plan is model-written: a step with no selector has nothing to click
            optional = bool(step.get("optional"))
            wait_s = float(step.get("wait") or 2)
            try:
                el = WebDriverWait(self.driver, 8 if not optional else 4).until(
                    EC.element_to_be_clickable(
                        (By.XPATH if step.get("by") == "xpath" else By.CSS_SELECTOR, step["selector"])
                    )
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                el.click()
                time.sleep(wait_s)
            except TimeoutException:
                if not optional:
                    logger.warning("Required ready step failed: %s", step)
            except Exception as e:
                if not optional:
                    logger.warning("Ready step error: %s", e)

    def open_entry(self):
        load_page(self.driver, self.plan.entry_url)
        time.sleep(2)
        self.run_ready_steps()
        try:
            WebDriverWait(self.driver, 12).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
        except TimeoutException:
            WebDriverWait(self.driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    def get_max_pages(self) -> int:
        if self.plan.pagination_type != "link_href":
            return 1
        links = self.driver.find_elements(By.XPATH, "//a[contains(@href, 'Page$')]")
        nums = []
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r"Page\$(\d+)", href)
            if m:
                nums.append(int(m.group(1)))
        return max(nums) if nums else 1

    def navigate_page(self, page_num: int) -> bool:
        if page_num <= 1:
            return True
        if self.plan.pagination_type != "link_href":
            return False
        pat = self.plan.pagination_pattern.replace("${n}", str(page_num))
        try:
            link = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f"//a[contains(@href, '{pat}')]"))
            )
            link.click()
            time.sleep(2 if self.fast_mode else 3)
            WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            return True
        except Exception:
            return False

    def scrape_list_page(self, page_num: int) -> list[dict[str, Any]]:
        rows_out: list[dict[str, Any]] = []
        try:
            table = self.driver.find_element(By.CSS_SELECTOR, self.plan.table_selector)
        except NoSuchElementException:
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr"))) if tables else None
        if not table:
            return rows_out

        trs = table.find_elements(By.TAG_NAME, "tr")
        headers: list[str] = []
        id_col = self.plan.id_column_index
        for tr in trs:
            ths = tr.find_elements(By.TAG_NAME, "th")
            if ths:
                headers = [h.text.strip() for h in ths]
                if id_col is None and self.plan.id_field:
                    for i, h in enumerate(headers):
                        if self.plan.id_field.lower() in h.lower():
                            id_col = i
                            break
                break

        sample_for_ai: list[list[str]] = []
        for tr in trs:
            if tr.find_elements(By.TAG_NAME, "th"):
                continue
            tds = tr.find_elements(By.TAG_NAME, "td")
            if tds:
                sample_for_ai.append([c.text.strip()[:120] for c in tds])
            if len(sample_for_ai) >= 3:
                break

        if headers and self.intent and (not self.plan.column_map or not self._headers_mapped):
            from inspector import ai_map_table_columns

            mapping = ai_map_table_columns(
                self.intent,
                headers,
                sample_for_ai,
                table_selector=self.plan.table_selector,
            )
            if mapping.get("column_map"):
                self.plan.column_map = dict(mapping["column_map"])
                self._headers_mapped = True
            if mapping.get("id_field"):
                self.plan.id_field = str(mapping["id_field"])
            if mapping.get("id_column_index") is not None:
                self.plan.id_column_index = int(mapping["id_column_index"])

        if not headers:
            headers = list(self.plan.column_map.values()) or [f"col{i}" for i in range(max(len(r) for r in sample_for_ai) if sample_for_ai else 5)]

        row_idx = 0
        for tr in trs:
            if tr.find_elements(By.TAG_NAME, "th"):
                continue
            tds = tr.find_elements(By.TAG_NAME, "td")
            if not tds:
                continue
            values = [c.text.strip() for c in tds]
            if not any(values):
                continue
            row: dict[str, Any] = {}
            for field_name, header in (self.plan.column_map or {}).items():
                if not isinstance(header, str):
                    continue
                if header in headers:
                    idx = headers.index(header)
                    row[field_name] = values[idx] if idx < len(values) else ""
                elif field_name in ("Gazette ID", "id") and id_col is not None and id_col < len(values):
                    row[field_name] = values[id_col]
            for i, h in enumerate(headers):
                if h and h not in row.values():
                    row.setdefault(h, values[i] if i < len(values) else "")

            ext = (
                row.get(self.plan.id_field)
                or row.get("Gazette ID")
                or row.get("gazette_id")
                or row.get("id")
                or ""
            )
            if not ext:
                for v in values:
                    if re.match(r"^[A-Z0-9/-]{4,}$", v):
                        ext = v
                        row[self.plan.id_field] = v
                        break
            if not ext and values:
                ext = "|".join(values[:4])[:120]
                row[self.plan.id_field] = f"row_{page_num}_{row_idx}"
                row["_row_key"] = ext
            row_idx += 1
            if not ext:
                continue
            if not row.get(self.plan.id_field):
                row[self.plan.id_field] = str(ext)[:120]

            pdf_url = ""
            if self.plan.detail_mode == "url_template" and self.plan.direct_url_template:
                pdf_url = guard_detail_url(
                    fill_url_template(self.plan.direct_url_template, row, self.plan.id_field)
                )
            elif self.plan.detail_mode == "none" and self.fast_mode:
                pdf_url = guess_pdf_url(str(ext))

            row["PDF_URL"] = pdf_url
            row["PDF_Text"] = ""
            rows_out.append(row)
            if self.on_progress:
                self.on_progress("row", str(ext))
        return rows_out

    def scrape_all(
        self,
        max_pages: int = 3,
        on_row: Callable[[dict[str, Any]], None] | None = None,
        check_exists: Callable[[str], bool] | None = None,
    ) -> int:
        processed = 0
        total_pages = min(self.get_max_pages(), max_pages)
        for p in range(1, total_pages + 1):
            if p > 1 and not self.navigate_page(p):
                continue
            page_rows, stop = self._scrape_with_stop(p, check_exists)
            for row in page_rows:
                if on_row:
                    on_row(row)
                processed += 1
            if stop:
                break
            time.sleep(0.5 if self.fast_mode else 2)
        return processed

    def _scrape_with_stop(
        self, page_num: int, check_exists: Callable[[str], bool] | None
    ) -> tuple[list[dict[str, Any]], bool]:
        rows = self.scrape_list_page(page_num)
        stop = False
        if not check_exists:
            return rows, stop
        filtered = []
        for row in rows:
            ext = str(row.get(self.plan.id_field) or row.get("Gazette ID") or "")
            if ext and check_exists(ext):
                stop = True
                break
            filtered.append(row)
        return filtered, stop
