"""
Persisted UI scrape sessions (multi-tab pipeline state).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "regulatory.sqlite"

_lock = threading.Lock()


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_ui_sessions() -> None:
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ui_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                job_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        try:
            cur.execute("ALTER TABLE ui_sessions ADD COLUMN user_id TEXT DEFAULT 'anonymous'")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        cur.close()
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _empty_payload() -> dict[str, Any]:
    return {
        "intent": None,
        "search_queries": [],
        "table_schema": None,
        "sources": [],
        "plan": None,
        "plans": [],
        "job_id": None,
        "prompt_draft": "",
        "keep_live": False,
        "goal": "",
        "messages": [],
        "archived": False,
        "run_events": [],
        "run_active": False,
        "awdax_run": None,
        "discovery_sources": [],
        "regulatory_feed_snapshot_ids": [],
        "regulatory_feed_active": False,
    }


def _row_to_session(row: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(row["payload_json"] or "{}")
    out = {
        "id": row["id"],
        "title": row["title"],
        "job_id": row["job_id"] or payload.get("job_id"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "user_id": row["user_id"] if "user_id" in row.keys() else "anonymous",
    }
    out.update(payload)
    return out


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ui_sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    return [
        {
            "id": r["id"],
            "title": r["title"],
            "job_id": r["job_id"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "has_intent": bool(json.loads(r["payload_json"] or "{}").get("intent")),
            "keep_live": bool(json.loads(r["payload_json"] or "{}").get("keep_live")),
        }
        for r in rows
    ]


def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ui_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        row = cur.fetchone()
        cur.close()
        conn.close()
    if not row:
        return None
    return _row_to_session(row)


def create_session(user_id: str, *, title: str = "New session") -> dict[str, Any]:
    init_ui_sessions()
    sid = uuid.uuid4().hex[:12]
    now = _now()
    payload = _empty_payload()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO ui_sessions (id, title, job_id, payload_json, created_at, updated_at, user_id)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, title.strip() or "Ne| session", None, json.dumps(payload), now, now, user_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    return get_session(sid, user_id) or {"id": sid, "title": title, "user_id": user_id, **_empty_payload()}


def save_session(user_id: str, session: dict[str, Any]) -> dict[str, Any]:
    init_ui_sessions()
    sid = str(session.get("id") or "")
    if not sid:
        raise ValueError("session id required")
    title = str(session.get("title") or "New session").strip() or "New session"
    job_id = session.get("job_id")
    payload = _empty_payload()
    for key in payload:
        if key in session:
            payload[key] = session[key]
    now = _now()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """UPDATE ui_sessions SET title=?, job_id=?, payload_json=?, updated_at=?
               WHERE id=? AND user_id=?""",
            (title, job_id, json.dumps(payload), now, sid, user_id),
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO ui_sessions (id, title, job_id, payload_json, created_at, updated_at, user_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (sid, title, job_id, json.dumps(payload), now, now, user_id),
            )
        conn.commit()
        cur.close()
        conn.close()
    saved = get_session(sid, user_id)
    if not saved:
        raise RuntimeError("failed to save session")
    return saved


def delete_session(session_id: str, user_id: str) -> bool:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM ui_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
    return deleted


def ensure_default_session(user_id: str) -> dict[str, Any]:
    sessions = list_sessions(user_id)
    if sessions:
        full = get_session(sessions[0]["id"], user_id)
        if full:
            return full
    return create_session(user_id, title="Session 1")