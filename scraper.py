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

import url_access
from row_limits import apply_period, period_for_intent
from discovery import SourceCandidate, fetch_html
from inspector import ScrapePlan
from reasoning import ScrapeIntent
from table_merge import merge_records

logger = logging.getLogger(__name__)

from listing_extract import (
    _extract_listing_rows,
    _fetch_html_for_gemini,
    _is_regulatory_table_plan,
    _finalize_extract_rows,
    _should_exhaust_listing,
    find_next_page_url,
    needs_browser,
)
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


MERGE_MAX_RECORDS = 20_000


def live_interval_seconds() -> int:
    """How often a live chat checks its sources again. One hour by default, which is what the app tells the user; each check
    reads every source with the AI, so a short interval costs real money for every chat left live."""
    try:
        return max(15, int(os.getenv("LIVE_SCRAPE_INTERVAL_SEC") or 3600))
    except ValueError:
        return 3600


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


def _file_owner(job: ScrapeJob, plan: ScrapePlan) -> str:
    return f"{job.job_id}|{plan.source_url or plan.entry_url}"


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

    def _job_status(self, job_id: str) -> dict[str, Any]:
        """The status dict of a job, built (with its database reads) only the first time."""
        st = self._status_by_job.get(job_id)
        if st is None:
            st = self._status_by_job[job_id] = self._default_job_status(job_id)
        return st

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
            st = self._job_status(job_id)
            st.update(kwargs)
            st["job_id"] = job_id
            # A per-row message (a new row was stored) is announced at most twice a second, and the record count (a count
            # over the whole table) is read at most once a second unless the phase changed: both ran for every row.
            clock = self.__dict__.setdefault("_status_clock", {})
            now = time.monotonic()
            if set(kwargs) == {"message"} and now - clock.get(("emit", job_id), 0.0) < 0.5:
                return
            clock[("emit", job_id)] = now
            st["live_enabled"] = self.is_job_live(job_id)
            st["is_running"] = self.is_job_running(job_id)
            if "phase" in kwargs or now - clock.get(("count", job_id), 0.0) >= 1.0:
                st["record_count"] = self._record_count(job_id)
                clock[("count", job_id)] = now
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
        *,
        conn: sqlite3.Connection | None = None,
    ) -> dict[str, Any] | None:
        """Keep one row. With `conn` (a connection the caller owns) the row is written on it and the caller commits: storing
        a source's rows on one connection with a commit every second is far cheaper than a connection and a disk sync per row."""
        # Never fall back to "the current job": that was one field shared by every user's run.
        id_field = plan.id_field if plan else "id"
        brand = str(row.get("brand") or "").strip()
        car = str(row.get("car_name") or row.get("name") or "").strip()
        ext = str(
            row.get("_uid")  # set when the page's id column is not unique (listing_extract._finalize_extract_rows)
            or (f"{brand}|{car}" if brand and car else "")
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
        shared = conn is not None
        if conn is None:
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
            if not shared:
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
            if not shared:
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

    def cancel_job(self, job_id: str | None) -> None:
        """Stop a scrape pass at its next source or row (a paused or deleted chat). Rows already stored stay."""
        if job_id:
            self._cancelled_jobs = {*getattr(self, "_cancelled_jobs", set()), job_id}

    def is_cancelled(self, job_id: str | None) -> bool:
        return bool(job_id) and job_id in getattr(self, "_cancelled_jobs", ())

    def _clear_cancel(self, job_id: str) -> None:
        self._cancelled_jobs = {j for j in getattr(self, "_cancelled_jobs", set()) if j != job_id}

    def start_live(self, plans: list[ScrapePlan], job: ScrapeJob, max_pages: int = 3) -> dict[str, Any]:
        jid = job.job_id
        self._clear_cancel(jid)
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
        interval = live_interval_seconds()
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

    def delete_job(self, job_id: str | None) -> None:
        """Remove everything a job left behind: rows, merged table, and its prompt, plans and sources. For a deleted
        chat or a replaced run, so a user's prompt doesn't outlive their chat."""
        if not job_id:
            return
        init_universal_tables()
        conn = _get_db()
        try:
            with conn:
                for table in ("records", "merged_tables", "scrape_plans", "sources"):
                    conn.execute(f"DELETE FROM {table} WHERE job_id=?", (job_id,))  # noqa: S608 - fixed names
                conn.execute("DELETE FROM scrape_jobs WHERE id=?", (job_id,))
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
        # Every record, not the default 500: a bigger run used to be cut off here without a word.
        raw = self.list_raw_records(job.job_id, limit=MERGE_MAX_RECORDS)
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
        self._clear_cancel(jid)
        with self._lock:
            if jid in self._running_jobs:
                return {"started": False, "reason": "already_running", **self.get_scrape_status(jid)}
            if jid in self._live:
                return {"started": False, "reason": "live_mode_active", **self.get_scrape_status(jid)}
            job.plans = plans
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

    def _on_row(self, plan: ScrapePlan, job: ScrapeJob, row: dict[str, Any], conn: sqlite3.Connection | None = None) -> None:
        """Keep, store and announce one scraped row. Writes the database: call it from the run's own thread only."""
        from row_quality import filter_vehicle_rows, intent_expects_priced_catalog, topic_is_vehicles

        source_url = plan.source_url or plan.entry_url
        columns = (job.table_schema or {}).get("columns") or []
        period = period_for_intent(job.intent)
        if period and not apply_period([row], columns, period)[0]:
            # Dated outside the period the user asked for ("between 2010 and 2025"): never stored.
            st = self._job_status(job.job_id)
            st["outside_period"] = int(st.get("outside_period") or 0) + 1
            return
        if not filter_vehicle_rows(
            [row],
            columns,
            catalog_with_prices=intent_expects_priced_catalog(
                job.intent.raw_prompt if job.intent else "",
                job.intent.topic if job.intent else "",
            ),
            vehicle=topic_is_vehicles(job.intent.raw_prompt if job.intent else "", job.intent.topic if job.intent else ""),
        ):
            return
        if "source_url" in columns and not row.get("source_url"):
            row["source_url"] = source_url
        item = self.store_record(job.job_id, source_url, row, plan=plan, conn=conn) if conn is not None else self.store_record(job.job_id, source_url, row, plan=plan)
        if item:
            is_new = bool(item.pop("is_new", True))
            jid = job.job_id
            if is_new:
                st = self._job_status(jid)
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
        st = self._job_status(job.job_id)
        outside_before = int(st.get("outside_period") or 0)
        conn = _get_db() if len(rows) > 1 else None
        last_commit = time.monotonic()
        try:
            for row in rows:
                if self.is_cancelled(job.job_id):
                    break
                self._on_row(plan, job, row, conn)
                if conn is not None and time.monotonic() - last_commit >= 1.0:
                    conn.commit()  # visible to the table the live view builds, about once a second
                    last_commit = time.monotonic()
        finally:
            if conn is not None:
                try:
                    conn.commit()
                finally:
                    conn.close()
            if plan.dataset_files:
                # The data files of this source were only kept until their rows were stored.
                import dataset_files

                dataset_files.release(_file_owner(job, plan))
        dropped = int(st.get("outside_period") or 0) - outside_before
        if dropped:
            period = period_for_intent(job.intent)
            self.emit_event(
                "log",
                {
                    "level": "info",
                    "message": f"{plan.source_name}: {dropped} rows dated outside {period.label() if period else 'the period'} left out",
                    "channel": "universal",
                },
            )
        return len(rows)

    def _listing_rows(self, plan: ScrapePlan, job: ScrapeJob, max_pages: int = 1) -> list[dict[str, Any]]:
        """Fetch a listing page and pull its rows with the LLM, then follow its "next page" links up to `max_pages` pages.
        No database writes, so it is safe on a worker thread."""
        if self.is_cancelled(job.job_id):
            return []
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
        if plan.dataset_files:
            return self._file_rows(plan, job, schema)
        plain = fetch_html(source_url)
        if not scroll_listing and (plan.feed or needs_browser(plain.get("html") or "")) and os.getenv("DATA_FEEDS", "1") != "0":
            # A JavaScript table: read the data feed behind it (every page of it), not the one page on screen.
            fed = self._feed_rows(plan, job, schema, source_url)
            if fed:
                return fed
        if not scroll_listing and os.getenv("AX_READER", "1") != "0" and (plan.render or needs_browser(plain.get("html") or "")):
            # A page built by JavaScript: read what the browser shows, page after page, through its accessibility tree.
            rows = self._browser_rows(plan, job, schema, source_url, max_pages)
            if rows:
                return rows
        html = _fetch_html_for_gemini(plan, source_url, scroll_listing=scroll_listing, job_id=job.job_id, fetched=plain)
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
        if rows and not scroll_listing and max_pages > 1:
            rows = self._follow_pages(plan, job, schema, rows, html, source_url, max_pages)
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

    def _browser_rows(self, plan: ScrapePlan, job: ScrapeJob, schema: dict[str, Any], source_url: str, max_pages: int) -> list[dict[str, Any]]:
        """Rows from a page opened in Chrome and read through its accessibility tree (ax_reader). When the page has a pager (a
        "Next" or "Go to next page" control) it is pressed, up to `max_pages` pages, stopping at the end of the list, a page
        that gives nothing new, or a pager that changes nothing. [] means the page could not be read this way."""
        import ax_reader
        from gemini_scrape import gemini_extract_rows_from_tree
        from inspector import _setup_driver, load_page, wait_until_settled

        columns = list(schema.get("columns") or [])
        pages = max(1, min(int(max_pages or 1), int(os.getenv("AX_MAX_PAGES", "10"))))

        def log(message: str, level: str = "info") -> None:
            self.emit_event("log", {"level": level, "message": f"{plan.source_name}: {message}", "channel": "universal"})

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        driver = None
        try:
            driver = _setup_driver()
            load_page(driver, source_url)
            wait_until_settled(driver)
            for n in range(1, pages + 1):
                if self.is_cancelled(job.job_id):
                    break
                ax = ax_reader.nodes(driver)
                tree = ax_reader.tree_text(ax)
                if len(tree) < 200:
                    break
                got = gemini_extract_rows_from_tree(
                    tree, job.intent, columns, page_url=source_url, source_name=plan.source_name, column_labels=schema.get("column_labels")
                )
                fresh = ax_reader.fresh_rows(got, seen)
                log(f"page {n} read from the accessibility tree: {len(fresh)} new rows")
                if not fresh:
                    break
                rows += fresh
                if n >= pages:
                    break
                target = ax_reader.pager_target(ax)
                if target is None or not ax_reader.advance(driver, ax, target):
                    break
        except Exception as e:  # noqa: BLE001 - what was read is kept; nothing read falls back to the page's HTML
            url_access.record_failure(job.job_id, source_url, stage=url_access.SCRAPE, outcome="error", reason=f"Browser reading failed: {e}")
            log(f"browser reading stopped ({e})", "warning")
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:  # noqa: BLE001
                    pass
        return _finalize_extract_rows(rows, plan, intent=job.intent, columns=columns) if rows else []

    def _file_rows(self, plan: ScrapePlan, job: ScrapeJob, schema: dict[str, Any]) -> list[dict[str, Any]]:
        """Rows from the data files a source offers: each is downloaded to a temporary file, read and mapped to the table.
        The files are deleted by _store_rows once their rows are stored (dataset_files.release)."""
        import data_feed
        import dataset_files

        columns = list(schema.get("columns") or [])
        labels = list(schema.get("column_labels") or columns)
        goal = (job.intent.raw_prompt or job.intent.topic) if job.intent else ""
        max_rows = int(os.getenv("DATASET_MAX_ROWS", "5000"))
        rows: list[dict[str, Any]] = []
        for url in plan.dataset_files:
            if len(rows) >= max_rows:
                break
            def refused(reason: str, url: str = url) -> None:
                url_access.record_failure(job.job_id, url, stage=url_access.SCRAPE, outcome="blocked", reason=f"Plain download refused ({reason}); fetched with the browser")

            try:
                records = dataset_files.records_from(url, owner=_file_owner(job, plan), on_refused=refused)
            except Exception as e:  # noqa: BLE001 - one unreadable file is recorded and skipped
                url_access.record_failure(job.job_id, url, stage=url_access.SCRAPE, outcome="error", reason=f"Data file not read: {e}")
                self.emit_event("log", {"level": "warning", "message": f"{plan.source_name}: file not read ({e})", "channel": "universal"})
                continue
            if not records:
                continue
            # A file is a whole dataset: keep the rows the request names (a country, a category), then those in its period,
            # and only then apply the row cap, so the cap never cuts away the rows that were asked for.
            filters = data_feed.value_filters(records, goal)
            if filters:
                records = data_feed.apply_value_filters(records, filters)
                self.emit_event("log", {"level": "info", "message": f"{plan.source_name}: kept rows where {filters}", "channel": "universal"})
            mapped = data_feed.to_rows(records, data_feed.column_mapping(records, columns, labels, goal))
            period = period_for_intent(job.intent)
            mapped = apply_period(mapped, columns, period)[0][: max_rows - len(rows)]
            self.emit_event(
                "log",
                {"level": "info", "message": f"{plan.source_name}: data file {url.rsplit('/', 1)[-1][:60]} gave {len(mapped)} rows", "channel": "universal"},
            )
            for row in mapped:
                if not row.get("source_url"):
                    row["source_url"] = url
            rows += mapped
        return _finalize_extract_rows(rows, plan, intent=job.intent, columns=columns) if rows else []

    def _feed_rows(self, plan: ScrapePlan, job: ScrapeJob, schema: dict[str, Any], source_url: str) -> list[dict[str, Any]]:
        """Rows from the data feed behind a JavaScript table (data_feed), finalised like extracted rows. [] when the page
        has no matching feed, so the caller reads the page instead."""
        import data_feed

        columns = list(schema.get("columns") or [])
        labels = list(schema.get("column_labels") or columns)
        period = period_for_intent(job.intent)

        def log(message: str) -> None:
            self.emit_event("log", {"level": "info", "message": f"{plan.source_name}: {message}", "channel": "universal"})

        def failed(url: str, reason: str) -> None:
            url_access.record_failure(job.job_id, url, stage=url_access.SCRAPE, outcome="error", reason=reason)

        found = data_feed.Feed.from_dict(plan.feed) if plan.feed else None
        rows = data_feed.read_feed(
            source_url,
            goal=(job.intent.raw_prompt or job.intent.topic) if job.intent else "",
            columns=columns,
            labels=labels,
            period=(period.start, period.end) if period else None,
            on_fail=failed,
            log=log,
            feed=found,
        )
        if not rows:
            return []
        return _finalize_extract_rows(rows, plan, intent=job.intent, columns=columns)

    def _follow_pages(
        self,
        plan: ScrapePlan,
        job: ScrapeJob,
        schema: dict[str, Any],
        rows: list[dict[str, Any]],
        html: str,
        source_url: str,
        max_pages: int,
    ) -> list[dict[str, Any]]:
        """The rest of a paginated listing: follow "next" until `max_pages`, a page with nothing new, or the end. A page that
        cannot be fetched ends the walk but keeps what was read."""
        key = plan.id_field or "id"
        have = {str(r.get(key) or "").lower() for r in rows}
        seen = {source_url.rstrip("/")}
        url = find_next_page_url(html, source_url)
        for _ in range(max_pages - 1):
            if not url or url.rstrip("/") in seen:
                break
            seen.add(url.rstrip("/"))
            try:
                fetched = fetch_html(url)
            except Exception as e:
                logger.info("%s: next page not read (%s)", plan.source_name, e)
                break
            if url_access.record_probe(job.job_id, url, fetched, stage=url_access.SCRAPE):
                break
            page = fetched.get("html") or ""
            if len(page) < 400:
                break
            more = _extract_listing_rows(page, job.intent, schema, page_url=url, plan=plan)
            fresh = [r for r in more if str(r.get(key) or "").lower() not in have]
            self.emit_event(
                "log",
                {"level": "info", "message": f"{plan.source_name}: next page gave {len(fresh)} new rows", "channel": "universal"},
            )
            if not fresh:  # nothing new: the list is over, or the "next" link goes round in a circle
                break
            have.update(str(r.get(key) or "").lower() for r in fresh)
            rows = rows + fresh
            url = find_next_page_url(page, url)
        return rows

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

        return self._store_rows(plan, job, self._listing_rows(plan, job, max_pages))

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
                ahead = {id(p): pool.submit(self._listing_rows, p, job, max_pages) for p in ahead_plans} if pool else {}
                for i, plan in enumerate(plans):
                    if self.is_cancelled(jid):
                        break
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
