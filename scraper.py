"""
Plan-driven universal scraper engine + job storage and orchestration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

import sqlite3

from discovery import SourceCandidate
from inspector import ScrapePlan, egazette_preset_plan, load_page, page_load_seconds
from reasoning import ScrapeIntent, parse_prompt
from table_merge import merge_records
from url_guard import UnresolvableHost, UnsafeURL, check_url

logger = logging.getLogger(__name__)

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, TimeoutException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from discovery import fetch_html  # noqa: E402
from RegulatoryFeed import _get_db, guess_pdf_url  # noqa: E402


_UNIVERSAL_DB_INIT = False
_UNIVERSAL_DB_LOCK = threading.Lock()


def init_universal_tables(conn: sqlite3.Connection | None = None) -> None:
    global _UNIVERSAL_DB_INIT
    if _UNIVERSAL_DB_INIT:
        return
    with _UNIVERSAL_DB_LOCK:
        if _UNIVERSAL_DB_INIT:
            return
        c = conn if conn is not None else _get_db()
        try:
            c.executescript(
                """
            CREATE TABLE IF NOT EXISTS scrape_jobs (
                id TEXT PRIMARY KEY,
                intent_json TEXT,
                status TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                url TEXT,
                title TEXT,
                legit_score REAL,
                meta_json TEXT
            );
            CREATE TABLE IF NOT EXISTS scrape_plans (
                job_id TEXT PRIMARY KEY,
                plan_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                source_url TEXT,
                external_id TEXT,
                data_json TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(job_id, external_id)
            );
            CREATE TABLE IF NOT EXISTS merged_tables (
                job_id TEXT PRIMARY KEY,
                columns_json TEXT,
                rows_json TEXT,
                labels_json TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
                """
            )
            c.commit()
            _UNIVERSAL_DB_INIT = True
        finally:
            if conn is None:
                c.close()


@dataclass
class ScrapeJob:
    job_id: str
    intent: ScrapeIntent
    source: SourceCandidate | None = None
    plan: ScrapePlan | None = None
    plans: list[ScrapePlan] | None = None
    status: str = "pending"
    records_saved: int = 0
    table_schema: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "intent": self.intent.to_dict(),
            "source": self.source.to_dict() if self.source else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "plans": [p.to_dict() for p in self.plans] if self.plans else None,
            "status": self.status,
            "records_saved": self.records_saved,
            "table_schema": self.table_schema,
        }


def _strip_html_tags(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def extract_tables_from_html(html: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for block in re.findall(r"<table\b[^>]*>(.*?)</table>", html, re.I | re.S):
        headers = [_strip_html_tags(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", block, re.I | re.S)]
        headers = [h for h in headers if h]
        rows: list[list[str]] = []
        for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", block, re.I | re.S):
            if re.search(r"<th\b", tr, re.I):
                continue
            cells = [_strip_html_tags(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.I | re.S)]
            cells = [c for c in cells if c]
            if cells:
                rows.append(cells)
        if headers or rows:
            tables.append({"headers": headers, "rows": rows})
    return tables


def _finalize_extract_rows(
    rows: list[dict[str, Any]],
    plan: ScrapePlan,
    *,
    intent: ScrapeIntent | None = None,
    columns: list[str] | None = None,
) -> list[dict[str, Any]]:
    id_field = plan.id_field or "car_name"
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        brand = str(row.get("brand") or "").strip()
        car = str(row.get("car_name") or row.get("name") or "").strip()
        ext = (f"{brand}|{car}" if brand and car else "") or row.get(id_field) or car or row.get("_row_key") or ""
        if not ext:
            row[id_field] = f"row_{i}"
        elif not row.get(id_field):
            row[id_field] = str(ext)[:120]
        row.setdefault("PDF_URL", "")
        row.setdefault("PDF_Text", "")
        out.append(row)

    from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

    cols = columns or []
    catalog_prices = bool(intent and intent_expects_priced_catalog(intent.raw_prompt, intent.topic))
    return filter_vehicle_rows(out, cols or None, catalog_with_prices=catalog_prices)


def _extract_listing_rows(
    html: str,
    intent: ScrapeIntent,
    schema: dict[str, Any],
    *,
    page_url: str,
    plan: ScrapePlan,
) -> list[dict[str, Any]]:
    columns = schema.get("columns") or []
    if not columns:
        return []
    from gemini_scrape import gemini_extract_rows_from_page

    rows = gemini_extract_rows_from_page(
        html,
        intent,
        columns,
        page_url=page_url,
        source_name=plan.source_name,
        column_labels=schema.get("column_labels"),
    )
    return _finalize_extract_rows(rows, plan, intent=intent, columns=columns)


def _is_regulatory_table_plan(plan: ScrapePlan) -> bool:
    url = (plan.entry_url or plan.source_url or "").lower()
    return plan.table_selector == "#gvGazetteList" or "egazette.gov.in" in url


def _fetch_html_for_gemini(
    plan: ScrapePlan,
    source_url: str,
    *,
    scroll_listing: bool,
) -> str:
    fetched = fetch_html(source_url)
    html = fetched.get("html") or ""
    if not scroll_listing:
        return html

    scraper = PlanDrivenScraper(plan, fast_mode=os.getenv("SCRAPE_FAST", "1") == "1")
    scraper.setup_driver()
    try:
        scraper.open_entry()
        from listing_scrape import selenium_scroll_and_get_html

        return selenium_scroll_and_get_html(scraper.driver) or scraper.driver.page_source or html
    finally:
        scraper.quit()


def _should_exhaust_listing(url: str, intent: ScrapeIntent) -> bool:
    from listing_sources import intent_wants_ev_catalog, is_aggregator_listing_url

    if is_aggregator_listing_url(url):
        return True
    return intent_wants_ev_catalog(intent) and any(
        h in (url or "").lower() for h in ("carwale", "cardekho", "91wheels", "zigwheels", "wikipedia.org/wiki")
    )


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
    return template.format(year=year, num=num, id=ext_id)


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
        opts = Options()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        if headless:
            opts.add_argument("--headless=new")
            opts.add_argument("--window-size=1920,1080")
        self.driver = webdriver.Chrome(options=opts)
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
            if action != "click":
                continue
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


@dataclass
class _LiveRunner:
    stop: threading.Event
    thread: threading.Thread
    plans: list[ScrapePlan]
    job: ScrapeJob
    max_pages: int


class UniversalScrapeService:
    def __init__(self):
        init_universal_tables()
        self._lock = threading.Lock()
        self._running_jobs: set[str] = set()
        self._live: dict[str, _LiveRunner] = {}
        self._status_by_job: dict[str, dict[str, Any]] = {}
        self.scrape_status: dict[str, Any] = {
            "phase": "idle",
            "message": "Universal scraper idle",
            "last_error": None,
            "rows_this_run": 0,
            "gazette_count": 0,
            "job_id": None,
            "live_enabled": False,
        }
        self._subscribers: list[queue.Queue] = []
        self._event_lock = threading.Lock()
        self._current_job: ScrapeJob | None = None

    @property
    def is_running(self) -> bool:
        return bool(self._running_jobs)

    @property
    def live_enabled(self) -> bool:
        return bool(self._live)

    def is_job_running(self, job_id: str | None) -> bool:
        if not job_id:
            return False
        return job_id in self._running_jobs

    def is_job_live(self, job_id: str | None) -> bool:
        if not job_id:
            return False
        return job_id in self._live

    def live_job_ids(self) -> list[str]:
        return list(self._live.keys())

    def _default_job_status(self, job_id: str) -> dict[str, Any]:
        return {
            "phase": "idle",
            "message": "Idle",
            "last_error": None,
            "rows_this_run": 0,
            "gazette_count": 0,
            "job_id": job_id,
            "live_enabled": self.is_job_live(job_id),
            "is_running": self.is_job_running(job_id),
            "record_count": self._record_count(job_id),
        }

    def get_job_status(self, job_id: str | None) -> dict[str, Any]:
        if not job_id:
            return dict(self.scrape_status)
        st = dict(self._status_by_job.get(job_id) or self._default_job_status(job_id))
        st["job_id"] = job_id
        st["live_enabled"] = self.is_job_live(job_id)
        st["is_running"] = self.is_job_running(job_id)
        st["record_count"] = self._record_count(job_id)
        return st

    def get_overview(self) -> dict[str, Any]:
        return {
            "live_job_ids": self.live_job_ids(),
            "running_job_ids": list(self._running_jobs),
        }

    def subscribe_events(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=256)
        with self._event_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe_events(self, q: queue.Queue) -> None:
        with self._event_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def emit_event(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"type": event_type, "ts": time.time(), "channel": "universal"}
        if data:
            payload.update(data)
        with self._event_lock:
            for sub in list(self._subscribers):
                try:
                    sub.put_nowait(payload)
                except queue.Full:
                    try:
                        sub.get_nowait()
                        sub.put_nowait(payload)
                    except queue.Empty:
                        pass

    def get_scrape_status(self, job_id: str | None = None) -> dict[str, Any]:
        if job_id:
            return self.get_job_status(job_id)
        self.scrape_status["is_running"] = self.is_running
        self.scrape_status["live_enabled"] = self.live_enabled
        jid = self.scrape_status.get("job_id")
        self.scrape_status["record_count"] = self._record_count(jid)
        out = dict(self.scrape_status)
        out.update(self.get_overview())
        return out

    def _set_status(self, job_id: str | None = None, **kwargs: Any) -> None:
        if job_id:
            st = self._status_by_job.setdefault(job_id, self._default_job_status(job_id))
            st.update(kwargs)
            st["job_id"] = job_id
            st["live_enabled"] = self.is_job_live(job_id)
            st["is_running"] = self.is_job_running(job_id)
            st["record_count"] = self._record_count(job_id)
            self.scrape_status.update(st)
            self.emit_event("status", {**st, "channel": "universal"})
            self.emit_event("jobs_overview", {**self.get_overview(), "channel": "universal"})
            return
        self.scrape_status.update(kwargs)
        self.scrape_status["is_running"] = self.is_running
        self.scrape_status["live_enabled"] = self.live_enabled
        self.emit_event("status", {**self.get_scrape_status(), "channel": "universal"})

    def _record_count(self, job_id: str | None) -> int:
        if not job_id:
            return 0
        conn = _get_db()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM records WHERE job_id=?", (job_id,))
        n = cur.fetchone()[0]
        cur.close()
        conn.close()
        return int(n)

    def load_intent(self, job_id: str) -> ScrapeIntent | None:
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        cur.execute("SELECT intent_json FROM scrape_jobs WHERE id=?", (job_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row or not row["intent_json"]:
            return None
        try:
            return ScrapeIntent.from_dict(json.loads(row["intent_json"]))
        except Exception:
            return None

    def save_job(self, job: ScrapeJob) -> None:
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO scrape_jobs (id, intent_json, status, updated_at) VALUES (?,?,?,datetime('now'))",
            (job.job_id, json.dumps(job.intent.to_dict()), job.status),
        )
        if job.plans:
            cur.execute(
                "INSERT OR REPLACE INTO scrape_plans (job_id, plan_json, updated_at) VALUES (?,?,datetime('now'))",
                (job.job_id, json.dumps([p.to_dict() for p in job.plans])),
            )
        elif job.plan:
            cur.execute(
                "INSERT OR REPLACE INTO scrape_plans (job_id, plan_json, updated_at) VALUES (?,?,datetime('now'))",
                (job.job_id, json.dumps(job.plan.to_dict())),
            )
        conn.commit()
        cur.close()
        conn.close()

    def store_record(
        self,
        job_id: str,
        source_url: str,
        row: dict[str, Any],
        plan: ScrapePlan | None = None,
    ) -> dict[str, Any] | None:
        active_plan = plan or (self._current_job.plan if self._current_job else None)
        id_field = active_plan.id_field if active_plan else "id"
        brand = str(row.get("brand") or "").strip()
        car = str(row.get("car_name") or row.get("name") or "").strip()
        ext = str(
            (f"{brand}|{car}" if brand and car else "")
            or row.get(id_field)
            or row.get("Gazette ID")
            or row.get("gazette_id")
            or row.get("id")
            or row.get("_row_key")
            or ""
        )
        if not ext:
            ext = hashlib.md5(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()[:16]
        host = urlparse(source_url).netloc or "source"
        external_id = f"{host}:{ext}"[:220]
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT 1 FROM records WHERE job_id=? AND external_id=? LIMIT 1",
                (job_id, external_id),
            )
            is_new = cur.fetchone() is None
            cur.execute(
                """INSERT INTO records (job_id, source_url, external_id, data_json)
                   VALUES (?,?,?,?)
                   ON CONFLICT(job_id, external_id) DO UPDATE SET data_json=excluded.data_json""",
                (job_id, source_url, external_id, json.dumps(row)),
            )
            conn.commit()
            cur.execute(
                "SELECT id, job_id, source_url, external_id, data_json, created_at FROM records WHERE job_id=? AND external_id=?",
                (job_id, external_id),
            )
            r = cur.fetchone()
            if not r:
                return None
            data = json.loads(r["data_json"])
            title = (
                data.get("car_name")
                or data.get("model")
                or data.get("name")
                or data.get("subject")
                or data.get("Subject")
                or data.get("topic")
                or ext.split(":", 1)[-1]
            )
            item = {
                "id": r["id"],
                "job_id": r["job_id"],
                "external_id": r["external_id"],
                "source_url": r["source_url"],
                "subject": title,
                "data": data,
                "summary": data.get("summary") or "",
                "gazette_id": external_id,
                "ministry": data.get("ministry") or data.get("Ministry / Organization"),
                "publish_date": data.get("publish_date") or data.get("Publish Date"),
                "pdf_url": data.get("PDF_URL") or "",
                "importance": data.get("importance") or "medium",
                "market_impact": data.get("market_impact") or "",
                "created_at": r["created_at"],
                "is_new": is_new,
            }
            return item
        finally:
            cur.close()
            conn.close()

    def _merged_row_keys(self, job: ScrapeJob) -> set[str]:
        from table_merge import _merge_row_key

        cols = (job.table_schema or {}).get("columns") or []
        if not cols:
            return set()
        table = self.get_merged_table(job.job_id)
        if not table:
            return set()
        out: set[str] = set()
        for r in table.get("rows") or []:
            k = _merge_row_key(r, cols)
            if k:
                out.add(k)
        return out

    def start_live(self, plans: list[ScrapePlan], job: ScrapeJob, max_pages: int = 3) -> dict[str, Any]:
        jid = job.job_id
        with self._lock:
            if jid in self._running_jobs:
                return {"started": False, "reason": "already_running", **self.get_scrape_status(jid)}
            if jid in self._live:
                return {"started": False, "reason": "live_already", **self.get_scrape_status(jid)}
            stop = threading.Event()
            thread = threading.Thread(
                target=self._live_loop,
                args=(jid,),
                daemon=True,
                name=f"live-scrape-{jid[:8]}",
            )
            runner = _LiveRunner(stop=stop, thread=thread, plans=plans, job=job, max_pages=max_pages)
            self._current_job = job
            self.save_job(job)
            self._live[jid] = runner
            # Running from now, as trigger_scrape_all does, not from when the thread reaches _run_all: the
            # orchestrator polls is_job_running right after this returns and would post "Run complete" with no rows.
            self._running_jobs.add(jid)
            try:
                thread.start()
            except Exception:
                self._running_jobs.discard(jid)
                self._live.pop(jid, None)
                raise
        self._set_status(
            jid,
            phase="live",
            message="Live mode started — watching for new data",
            live_enabled=True,
        )
        return {"started": True, "live": True, "job_id": jid, **self.get_scrape_status(jid)}

    def stop_live(self, job_id: str | None = None) -> dict[str, Any]:
        targets: list[str]
        with self._lock:
            if job_id:
                targets = [job_id] if job_id in self._live else []
            else:
                targets = list(self._live.keys())
            for jid in targets:
                self._live[jid].stop.set()
        for jid in targets:
            self._set_status(jid, phase="idle", message="Live mode stopped", live_enabled=False)
        if not targets and job_id:
            return {"stopped": False, "reason": "not_live", **self.get_scrape_status(job_id)}
        return {"stopped": True, "job_ids": targets, **self.get_overview()}

    def _live_loop(self, job_id: str) -> None:
        interval = max(15, int(os.getenv("LIVE_SCRAPE_INTERVAL_SEC", "90")))
        while True:
            with self._lock:
                runner = self._live.get(job_id)
                if not runner or runner.stop.is_set():
                    break
                plans, job, max_pages = runner.plans, runner.job, runner.max_pages
            try:
                self._run_all(plans, job, max_pages, from_live=True)
            except Exception as e:
                logger.error("Live scrape cycle failed (%s): %s", job_id, e)
                self.emit_event(
                    "log",
                    {
                        "level": "error",
                        "message": f"Live cycle ({job_id[:8]}): {e}",
                        "job_id": job_id,
                        "channel": "universal",
                    },
                )
            with self._lock:
                runner = self._live.get(job_id)
                if not runner or runner.stop.is_set():
                    break
            self._set_status(
                job_id,
                phase="live",
                message=f"Live — next check in {interval}s",
                live_enabled=True,
            )
            if runner.stop.wait(timeout=interval):
                break
        with self._lock:
            self._live.pop(job_id, None)
            # start_live marked it running; a loop stopped before its first cycle never reached _run_all's clear.
            self._running_jobs.discard(job_id)
        self._set_status(job_id, phase="idle", message="Live mode stopped", live_enabled=False)

    def list_raw_records(self, job_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT source_url, data_json FROM records WHERE job_id=? ORDER BY id ASC LIMIT ?",
            (job_id, limit),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({"source_url": r["source_url"], "data": json.loads(r["data_json"])})
        return out

    def clear_job_dataset(self, job_id: str | None) -> None:
        """Remove one job's raw and merged rows without deleting its job metadata."""
        if not job_id:
            return
        init_universal_tables()
        conn = _get_db()
        try:
            with conn:
                conn.execute("DELETE FROM records WHERE job_id=?", (job_id,))
                conn.execute("DELETE FROM merged_tables WHERE job_id=?", (job_id,))
        finally:
            conn.close()

    def save_merged_table(self, job_id: str, table: dict[str, Any]) -> None:
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO merged_tables (job_id, columns_json, rows_json, labels_json, updated_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(job_id) DO UPDATE SET
                 columns_json=excluded.columns_json,
                 rows_json=excluded.rows_json,
                 labels_json=excluded.labels_json,
                 updated_at=datetime('now')""",
            (
                job_id,
                json.dumps(table.get("columns") or []),
                json.dumps(table.get("rows") or []),
                json.dumps(table.get("column_labels") or []),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()

    def get_merged_table(self, job_id: str | None) -> dict[str, Any] | None:
        if not job_id:
            return None
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT columns_json, rows_json, labels_json FROM merged_tables WHERE job_id=?",
            (job_id,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        rows = json.loads(row["rows_json"])
        if not rows:
            return None
        return {
            "columns": json.loads(row["columns_json"]),
            "column_labels": json.loads(row["labels_json"]),
            "rows": rows,
            "row_count": len(rows),
        }

    def rebuild_merged_table(self, job: ScrapeJob) -> dict[str, Any]:
        raw = self.list_raw_records(job.job_id)
        schema = job.table_schema or {}
        table = merge_records(
            job.intent,
            raw,
            columns_override=schema.get("columns"),
            column_labels_override=schema.get("column_labels"),
        )
        self.save_merged_table(job.job_id, table)
        return table

    def list_records(self, job_id: str | None, limit: int = 50) -> list[dict[str, Any]]:
        init_universal_tables()
        conn = _get_db()
        cur = conn.cursor()
        if job_id:
            cur.execute(
                "SELECT id, external_id, data_json, created_at FROM records WHERE job_id=? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            )
        else:
            cur.execute(
                "SELECT id, external_id, data_json, created_at FROM records ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        out = []
        for r in rows:
            data = json.loads(r["data_json"])
            out.append(
                {
                    "id": r["id"],
                    "external_id": r["external_id"],
                    "subject": data.get("subject") or data.get("Subject") or r["external_id"],
                    "summary": data.get("summary") or "Pending summary…",
                    "gazette_id": r["external_id"],
                    "ministry": data.get("ministry") or data.get("Ministry / Organization"),
                    "publish_date": data.get("publish_date") or data.get("Publish Date"),
                    "pdf_url": data.get("PDF_URL") or "",
                    "importance": data.get("importance") or "medium",
                    "created_at": r["created_at"],
                }
            )
        return out

    def trigger_scrape(self, plan: ScrapePlan, job: ScrapeJob, max_pages: int = 3) -> dict[str, Any]:
        return self.trigger_scrape_all([plan], job, max_pages=max_pages)

    def trigger_scrape_all(
        self,
        plans: list[ScrapePlan],
        job: ScrapeJob,
        max_pages: int = 3,
        *,
        live: bool = False,
    ) -> dict[str, Any]:
        jid = job.job_id
        if live:
            return self.start_live(plans, job, max_pages=max_pages)
        with self._lock:
            if jid in self._running_jobs:
                return {"started": False, "reason": "already_running", **self.get_scrape_status(jid)}
            if jid in self._live:
                return {"started": False, "reason": "live_mode_active", **self.get_scrape_status(jid)}
            job.plans = plans
            self._current_job = job
            self.save_job(job)
            self._running_jobs.add(jid)
            t = threading.Thread(
                target=self._run_all,
                args=(plans, job, max_pages),
                kwargs={"from_live": False},
                daemon=True,
                name=f"scrape-{jid[:8]}",
            )
            try:
                t.start()
            except Exception:
                self._running_jobs.discard(jid)
                raise
            return {"started": True, "sources": len(plans), "job_id": jid, **self.get_scrape_status(jid)}

    def _run_single(self, plan: ScrapePlan, job: ScrapeJob, max_pages: int) -> int:
        source_url = plan.source_url or plan.entry_url
        schema = job.table_schema or {}
        columns = schema.get("columns") or []

        def on_row(row: dict[str, Any]):
            from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

            if not filter_vehicle_rows(
                [row],
                columns,
                catalog_with_prices=intent_expects_priced_catalog(
                    job.intent.raw_prompt if job.intent else "",
                    job.intent.topic if job.intent else "",
                ),
            ):
                return
            if "source_url" in columns and not row.get("source_url"):
                row["source_url"] = source_url
            item = self.store_record(job.job_id, source_url, row, plan=plan)
            if item:
                is_new = bool(item.pop("is_new", True))
                jid = job.job_id
                if is_new:
                    st = self._status_by_job.setdefault(jid, self._default_job_status(jid))
                    st["rows_this_run"] = int(st.get("rows_this_run") or 0) + 1
                    self.emit_event(
                        "item",
                        {"item": item, "update": False, "job_id": jid, "channel": "universal"},
                    )
                    self._set_status(jid, message=f"{plan.source_name}: new {item['external_id']}")
                elif self.is_job_live(jid):
                    self.emit_event(
                        "item",
                        {"item": item, "update": True, "job_id": jid, "channel": "universal"},
                    )

        if plan.blocked:
            self.emit_event(
                "log",
                {
                    "level": "warning",
                    "message": f"Skipping hard-blocked source: {plan.source_name}",
                    "channel": "universal",
                },
            )
            return 0

        if _is_regulatory_table_plan(plan):
            self.emit_event(
                "log",
                {"level": "info", "message": f"{plan.source_name}: regulatory table scrape (Selenium)…", "channel": "universal"},
            )
            scraper = PlanDrivenScraper(
                plan,
                fast_mode=os.getenv("SCRAPE_FAST", "1") == "1",
                intent=job.intent,
            )
            scraper.setup_driver()
            try:
                scraper.open_entry()
                self._set_status(job.job_id, phase="scraping", message=f"Scraping {plan.source_name}…")
                return scraper.scrape_all(max_pages=max_pages, on_row=on_row)
            finally:
                scraper.quit()

        if not columns or not job.intent:
            self.emit_event(
                "log",
                {"level": "warning", "message": f"{plan.source_name}: missing table schema or intent", "channel": "universal"},
            )
            return 0

        scroll_listing = _should_exhaust_listing(source_url, job.intent)
        self.emit_event(
            "log",
            {
                "level": "info",
                "message": f"{plan.source_name}: Gemini scrape — {'scroll + ' if scroll_listing else ''}fetch page…",
                "channel": "universal",
            },
        )
        html = _fetch_html_for_gemini(plan, source_url, scroll_listing=scroll_listing)
        if len(html) < 400:
            self.emit_event(
                "log",
                {"level": "warning", "message": f"{plan.source_name}: page HTML too short", "channel": "universal"},
            )
            return 0

        self.emit_event(
            "log",
            {"level": "info", "message": f"{plan.source_name}: Gemini extracting rows…", "channel": "universal"},
        )
        rows = _extract_listing_rows(html, job.intent, schema, page_url=source_url, plan=plan)
        if rows:
            self.emit_event(
                "log",
                {
                    "level": "info",
                    "message": f"{plan.source_name}: Gemini extracted {len(rows)} rows",
                    "channel": "universal",
                },
            )
            for row in rows:
                on_row(row)
            return len(rows)

        self.emit_event(
            "log",
            {"level": "warning", "message": f"{plan.source_name}: Gemini returned 0 rows", "channel": "universal"},
        )
        return 0

    def _run_all(self, plans: list[ScrapePlan], job: ScrapeJob, max_pages: int, *, from_live: bool = False) -> None:
        jid = job.job_id
        keys_before = self._merged_row_keys(job) if job.table_schema else set()
        self._running_jobs.add(jid)
        phase = "live_scraping" if from_live else "starting"
        self._set_status(
            jid,
            phase=phase,
            message=f"{'Live check' if from_live else 'Starting'} — {len(plans)} sources",
            rows_this_run=0,
            last_error=None,
            live_enabled=self.is_job_live(jid),
        )
        self.emit_event(
            "log",
            {
                "level": "info",
                "message": f"Job {jid} — {'live cycle' if from_live else 'scrape'} ({len(plans)} sources)",
                "job_id": jid,
                "channel": "universal",
            },
        )
        total_processed = 0
        errors: list[str] = []
        try:
            for i, plan in enumerate(plans):
                self.emit_event(
                    "log",
                    {"level": "info", "message": f"[{i + 1}/{len(plans)}] {plan.source_name}", "channel": "universal"},
                )
                try:
                    total_processed += self._run_single(plan, job, max_pages)
                except Exception as e:
                    errors.append(f"{plan.source_name}: {e}")
                    logger.error("Source scrape failed: %s", e)
                    self.emit_event("log", {"level": "error", "message": str(e), "channel": "universal"})
            job.status = "completed" if not errors else "partial"
            st = self._status_by_job.get(jid) or {}
            job.records_saved = int(st.get("rows_this_run") or 0)
            self.save_job(job)
            try:
                table = self.rebuild_merged_table(job)
                keys_after = self._merged_row_keys(job)
                new_catalog = len(keys_after - keys_before)
                self.emit_event(
                    "table",
                    {
                        "job_id": job.job_id,
                        "table": table,
                        "new_row_count": new_catalog,
                        "live_update": from_live or self.is_job_live(jid),
                        "channel": "universal",
                    },
                )
                log_msg = f"Merged table: {table.get('row_count', 0)} rows"
                if new_catalog:
                    log_msg += f" (+{new_catalog} new)"
                self.emit_event(
                    "log",
                    {"level": "info", "message": log_msg, "job_id": jid, "channel": "universal"},
                )
            except Exception as e:
                logger.warning("Merged table build failed: %s", e)
            msg = f"Done — {total_processed} rows across {len(plans)} sources, {job.records_saved} saved."
            if errors:
                msg += f" ({len(errors)} source errors)"
            if self.is_job_live(jid) and from_live:
                self._set_status(
                    jid,
                    phase="live",
                    message=msg + " — watching for updates",
                    last_error=errors[0] if errors else None,
                    live_enabled=True,
                )
            elif not self.is_job_live(jid):
                self._set_status(
                    jid,
                    phase="idle",
                    message=msg,
                    last_error=errors[0] if errors else None,
                )
        except Exception as e:
            logger.error("Universal scrape failed: %s", e)
            job.status = "error"
            self.save_job(job)
            if not self.is_job_live(jid):
                self._set_status(jid, phase="error", last_error=str(e), message=str(e))
        finally:
            self._running_jobs.discard(jid)
            self.emit_event("status", {**self.get_job_status(jid), "channel": "universal"})


universal_service = UniversalScrapeService()


def run_pipeline(
    prompt: str,
    *,
    source_index: int = 0,
    max_pages: int = 3,
    skip_inspect: str | None = None,
) -> ScrapeJob:
    intent = parse_prompt(prompt)
    job = ScrapeJob(job_id=intent.job_id, intent=intent, status="discovering")

    from regulatory_strategy import intent_uses_regulatory_feed, regulatory_feed_max_pages

    if intent_uses_regulatory_feed(intent):
        from RegulatoryFeed import feed_service

        pages = regulatory_feed_max_pages(max_pages)
        feed_service.trigger_scrape(max_pages=pages)
        job.status = "regulatory_feed"
        universal_service.save_job(job)
        return job

    if skip_inspect:
        with open(skip_inspect, encoding="utf-8") as f:
            plan = ScrapePlan.from_dict(json.load(f))
        job.plan = plan
        job.status = "ready"
        universal_service.trigger_scrape(plan, job, max_pages=max_pages)
        return job

    from inspector import discover_inspected_sources
    from query_generation import generate_search_queries

    queries = generate_search_queries(intent)
    sources, plans = discover_inspected_sources(intent, search_queries=queries)
    if not plans:
        raise RuntimeError("No inspected sources")
    job.plans = plans
    job.plan = plans[0] if plans else None
    job.status = "ready"
    universal_service.save_job(job)
    universal_service.trigger_scrape_all(plans, job, max_pages=max_pages)
    return job


def main() -> int:
    parser = argparse.ArgumentParser(description="Run universal scraper from plan JSON")
    parser.add_argument("--plan", help="ScrapePlan JSON file")
    parser.add_argument("--prompt", help="Full pipeline from prompt")
    parser.add_argument("--preset-egazette", action="store_true")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--skip-inspect", help="Use existing plan JSON with --prompt")
    args = parser.parse_args()

    if args.preset_egazette or (args.plan and "egazette" in (args.plan or "")):
        plan = egazette_preset_plan()
    elif args.plan:
        with open(args.plan, encoding="utf-8") as f:
            plan = ScrapePlan.from_dict(json.load(f))
    else:
        parser.error("Provide --plan or --preset-egazette or --prompt")

    if args.prompt:
        job = run_pipeline(
            args.prompt,
            max_pages=args.max_pages,
            skip_inspect=args.skip_inspect,
        )
        print(json.dumps(job.to_dict(), indent=2))
        return 0

    intent = ScrapeIntent(job_id=uuid.uuid4().hex[:12], topic=plan.source_name, raw_prompt="cli")
    job = ScrapeJob(job_id=intent.job_id, intent=intent, plan=plan, status="ready")
    universal_service.trigger_scrape(plan, job, max_pages=args.max_pages)
    print(json.dumps({"started": True, "job_id": job.job_id}, indent=2))
    time.sleep(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
