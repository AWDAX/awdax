"""
RegulatoryFeed – the eGazette feed service: its database, scrape cycle, summaries and redlines, background workers.
The pieces it drives live in gazette_scraper.py (Selenium), gazette_pdf.py (PDF text) and gazette_summary.py (LLM).
Uses local SQLite; imported by app.py as a service module.
"""

import json
import logging
import os
import queue
import re
import threading
import time
from typing import Any

import sqlite3


from gazette_pdf import _scrape_fast_mode, download_and_extract_pdf, filter_hindi_text, guess_pdf_url
from gazette_scraper import SELENIUM_AVAILABLE, GazetteScraper
from gazette_summary import AISummarizer

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
    conn = sqlite3.connect(_db_path(), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
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
# Scraping + processing service
# ---------------------------------------------------------------------------

class RegulatoryFeedService:
    def __init__(self):
        self.is_running = False
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
            self.is_running = True
            try:
                t.start()
            except Exception:
                self.is_running = False
                raise
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
        finally:
            cur.close()
            conn.close()

        if not row:
            return
        pdf_text = (row.get("pdf_text") or "").strip()
        pdf_url = row.get("pdf_url") or guess_pdf_url(row.get("gazette_id") or "")
        if len(pdf_text) >= 50 or not pdf_url:
            return

        # Download outside any open DB connection (c590915 restructuring).
        fetched = download_and_extract_pdf(pdf_url)
        if not fetched:
            return
        fetched = filter_hindi_text(fetched)

        conn = _get_db()
        cur = conn.cursor()
        try:
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
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            g = None
        finally:
            cur.close()
            conn.close()
        if not g:
            return
        try:
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
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return

        # Reopen only now that the LLM call is finished.
        conn = _get_db()
        cur = conn.cursor()
        try:
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

    BOOTSTRAP_TARGET = 100  # keep backfilling history until at least this many notifications

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
