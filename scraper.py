"""
Universal scrape service: job storage, the scrape run (sources in parallel, rows stored in order) and live mode.
The Selenium listing engine is plan_scraper.py; listing-page extraction is listing_extract.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import sqlite3

from discovery import SourceCandidate
from inspector import ScrapePlan
from reasoning import ScrapeIntent
from table_merge import merge_records

logger = logging.getLogger(__name__)

from listing_extract import _extract_listing_rows, _fetch_html_for_gemini, _is_regulatory_table_plan, _should_exhaust_listing
from plan_scraper import PlanDrivenScraper
from RegulatoryFeed import _get_db


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


def _scrape_workers() -> int:
    """How many listing pages the scrape fetches and reads at once (1 = one at a time). Some open a headless Chrome."""
    try:
        return max(1, int(os.getenv("SCRAPE_WORKERS", "3")))
    except ValueError:
        return 3


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

    def _on_row(self, plan: ScrapePlan, job: ScrapeJob, row: dict[str, Any]) -> None:
        """Keep, store and announce one scraped row. Writes the database: call it from the run's own thread only."""
        from row_quality import filter_vehicle_rows, intent_expects_priced_catalog

        source_url = plan.source_url or plan.entry_url
        columns = (job.table_schema or {}).get("columns") or []
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

    def _store_rows(self, plan: ScrapePlan, job: ScrapeJob, rows: list[dict[str, Any]]) -> int:
        for row in rows:
            self._on_row(plan, job, row)
        return len(rows)

    def _listing_rows(self, plan: ScrapePlan, job: ScrapeJob) -> list[dict[str, Any]]:
        """Fetch a listing page and pull its rows with the LLM. No database writes, so it is safe on a worker thread."""
        source_url = plan.source_url or plan.entry_url
        schema = job.table_schema or {}
        columns = schema.get("columns") or []
        if not columns or not job.intent:
            self.emit_event(
                "log",
                {"level": "warning", "message": f"{plan.source_name}: missing table schema or intent", "channel": "universal"},
            )
            return []

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
            return []

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
            return rows

        self.emit_event(
            "log",
            {"level": "warning", "message": f"{plan.source_name}: Gemini returned 0 rows", "channel": "universal"},
        )
        return []

    def _run_single(self, plan: ScrapePlan, job: ScrapeJob, max_pages: int) -> int:
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
                return scraper.scrape_all(max_pages=max_pages, on_row=lambda row: self._on_row(plan, job, row))
            finally:
                scraper.quit()

        return self._store_rows(plan, job, self._listing_rows(plan, job))

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
            # Listing pages are fetched and read SCRAPE_WORKERS at a time; rows are stored here, in source order,
            # so the database and the merge see exactly what one-at-a-time scraping gave. Selenium-driven
            # regulatory tables and blocked plans keep the sequential path (they write as they scrape).
            workers = _scrape_workers()
            ahead_plans = [p for p in plans if not p.blocked and not _is_regulatory_table_plan(p)]
            pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") if workers > 1 and len(ahead_plans) > 1 else None
            try:
                ahead = {id(p): pool.submit(self._listing_rows, p, job) for p in ahead_plans} if pool else {}
                for i, plan in enumerate(plans):
                    self.emit_event(
                        "log",
                        {"level": "info", "message": f"[{i + 1}/{len(plans)}] {plan.source_name}", "channel": "universal"},
                    )
                    try:
                        fetched = ahead.get(id(plan))
                        if fetched is not None:
                            total_processed += self._store_rows(plan, job, fetched.result())
                        else:
                            total_processed += self._run_single(plan, job, max_pages)
                    except Exception as e:
                        errors.append(f"{plan.source_name}: {e}")
                        logger.error("Source scrape failed: %s", e)
                        self.emit_event("log", {"level": "error", "message": str(e), "channel": "universal"})
            finally:
                if pool:
                    pool.shutdown(wait=True)
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
