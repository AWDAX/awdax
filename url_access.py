"""
Every link a run opens goes through one plain web request first (no browser). A link that fails it (refused, blocked, not
found, unreachable, behind a CAPTCHA) is recorded here, per run, so each chat has a dataset of the links it could not read
and why. A page that answers but only builds its content with JavaScript is not a failure: the browser renders it later.
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_ready = False

COLUMNS = ["url", "domain", "stage", "outcome", "http_status", "reason", "checked_at"]
LABELS = ["Link", "Site", "Step", "Outcome", "HTTP status", "Reason", "Checked at (UTC)"]

# The run step that asked for the link.
RESEARCH, SEARCH, INSPECT, SCRAPE = "research", "search", "inspect", "scrape"

_CAPTCHA = re.compile(r"g-recaptcha|hcaptcha|cf-challenge|challenge-platform|captcha-delivery|px-captcha", re.I)


def _db():
    from RegulatoryFeed import _get_db

    conn = _get_db()
    global _ready
    if not _ready:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS url_failures (
                job_id TEXT NOT NULL,
                url TEXT NOT NULL,
                stage TEXT NOT NULL,
                outcome TEXT NOT NULL,
                http_status INTEGER,
                reason TEXT,
                checked_at TEXT NOT NULL,
                PRIMARY KEY (job_id, url)
            )"""
        )
        conn.commit()
        _ready = True
    return conn


def classify(probe: dict[str, Any]) -> tuple[str, str] | None:
    """(outcome, reason) when a plain request's result means the page cannot be read; None when it answered.
    `probe` is what discovery.probe_https / fetch_html return."""
    status = int(probe.get("http_status") or 0)
    error = str(probe.get("error") or "")
    if probe.get("blocked"):
        return "not allowed", error or "This address is not allowed (private or local network)"
    if status in (401, 403):
        return "blocked", f"The site refused the request (HTTP {status})"
    if status == 429:
        return "blocked", "The site is rate-limiting requests (HTTP 429)"
    if status in (404, 410):
        return "not found", f"The page does not exist (HTTP {status})"
    if status >= 500:
        return "error", f"The site answered with a server error (HTTP {status})"
    if 400 <= status < 500:
        return "error", f"The site answered HTTP {status}"
    if status == 0 or not probe.get("https_ok", status == 200):
        return "unreachable", error or "No answer over HTTPS"
    html = str(probe.get("html") or "")[:20000]
    if html and len(_CAPTCHA.findall(html)) >= 1 and len(re.sub(r"<[^>]+>", " ", html).split()) < 400:
        return "captcha", "The page is a CAPTCHA or bot check"
    return None


def record_failure(job_id: str, url: str, *, stage: str, outcome: str, reason: str = "", http_status: int | None = None) -> None:
    """One row per link and run: the first step at which it failed (a link that failed its plain request is often
    tried again by the next step, which would only repeat the same failure)."""
    if not job_id or not url:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _lock:
            conn = _db()
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO url_failures (job_id, url, stage, outcome, http_status, reason, checked_at) VALUES (?,?,?,?,?,?,?)",
                    (job_id, url, stage, outcome, http_status or None, (reason or "")[:500], now),
                )
                conn.commit()
            finally:
                conn.close()
    except Exception as e:  # a failed bookkeeping write must never stop a run
        logger.warning("Could not record failed link %s: %s", url, e)


def record_probe(job_id: str, url: str, probe: dict[str, Any], *, stage: str) -> tuple[str, str] | None:
    """Classify a plain request and record it when it failed. Returns (outcome, reason) or None when the page answered."""
    failed = classify(probe)
    if failed:
        record_failure(job_id, url, stage=stage, outcome=failed[0], reason=failed[1], http_status=int(probe.get("http_status") or 0))
    return failed


def failures_for_job(job_id: str) -> list[dict[str, Any]]:
    if not job_id:
        return []
    with _lock:
        conn = _db()
        try:
            rows = conn.execute(
                "SELECT url, stage, outcome, http_status, reason, checked_at FROM url_failures WHERE job_id=? ORDER BY checked_at, url",
                (job_id,),
            ).fetchall()
        finally:
            conn.close()
    out = []
    for r in rows:
        url = r["url"]
        out.append({
            "url": url,
            "domain": (urlsplit(url).hostname or "").removeprefix("www."),
            "stage": r["stage"],
            "outcome": r["outcome"],
            "http_status": r["http_status"] or "",
            "reason": r["reason"] or "",
            "checked_at": r["checked_at"],
        })
    return out


def dataset_for_job(job_id: str) -> dict[str, Any]:
    """The failed links of a run as a table, in the same shape as the chat's dataset."""
    rows = failures_for_job(job_id)
    return {"columns": COLUMNS, "column_labels": LABELS, "rows": rows, "row_count": len(rows)}
