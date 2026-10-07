"""
Persisted UI scrape sessions (multi-tab pipeline state).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
# The same file as the scraper tables (RegulatoryFeed._db_path): SQLITE_PATH moves both, e.g. onto a server volume.
DB_PATH = Path(os.getenv("SQLITE_PATH") or ROOT / "regulatory.sqlite")

_lock = threading.Lock()
# DB file whose DDL has already run in this process (re-runs if DB_PATH is repointed, e.g. in tests).
_initialized: Path | None = None


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def init_ui_sessions() -> None:
    global _initialized
    with _lock:
        if _initialized == DB_PATH:
            return
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_ui_sessions_user ON ui_sessions(user_id, updated_at)")
        conn.commit()
        cur.close()
        conn.close()
        _initialized = DB_PATH


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
        "places_stats": None,
        # The web-research step: {"understanding", "websites": [ranked], "searched", "grounded_domains"}.
        "research": None,
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


def _require_user(user_id: str | None) -> str:
    """Every user-facing read/write is scoped to an owner; an empty id must never widen it to all users."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id required")
    return user_id


def _session_meta(r: sqlite3.Row) -> dict[str, Any]:
    payload = json.loads(r["payload_json"] or "{}")
    return {
        "id": r["id"],
        "title": r["title"],
        "job_id": r["job_id"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
        "has_intent": bool(payload.get("intent")),
        "keep_live": bool(payload.get("keep_live")),
    }


def _list_sessions(user_id: str | None) -> list[dict[str, Any]]:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        if user_id is None:
            cur.execute("SELECT * FROM ui_sessions ORDER BY updated_at DESC")
        else:
            cur.execute("SELECT * FROM ui_sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    return [_session_meta(r) for r in rows]


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    return _list_sessions(_require_user(user_id))


def list_full_sessions(user_id: str) -> list[dict[str, Any]]:
    """The account's sessions in full, newest first, in one read."""
    user_id = _require_user(user_id)
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM ui_sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
    return [_row_to_session(r) for r in rows]


def list_all_sessions_internal() -> list[dict[str, Any]]:
    """Every user's sessions. Only for server start-up recovery; never reachable from a request."""
    return _list_sessions(None)


def _get_session(session_id: str, user_id: str | None) -> dict[str, Any] | None:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        if user_id is None:
            cur.execute("SELECT * FROM ui_sessions WHERE id=?", (session_id,))
        else:
            cur.execute("SELECT * FROM ui_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        row = cur.fetchone()
        cur.close()
        conn.close()
    if not row:
        return None
    return _row_to_session(row)


def get_session(session_id: str, user_id: str) -> dict[str, Any] | None:
    return _get_session(session_id, _require_user(user_id))


def get_session_internal(session_id: str) -> dict[str, Any] | None:
    """A session by id alone, for background threads that act for a chat the request path already authorised."""
    return _get_session(session_id, None)


def create_session(user_id_or_title: str | None = None, *, user_id: str | None = None, title: str | None = None) -> dict[str, Any]:
    init_ui_sessions()
    actual_user_id = user_id or "anonymous"
    actual_title = title or "New session"
    if user_id_or_title is not None:
        if user_id is None and title is None:
            actual_title = user_id_or_title
        elif user_id is None:
            actual_user_id = user_id_or_title
    sid = uuid.uuid4().hex[:12]
    now = _now()
    payload = _empty_payload()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO ui_sessions (id, title, job_id, payload_json, created_at, updated_at, user_id)
               VALUES (?,?,?,?,?,?,?)""",
            (sid, actual_title.strip() or "New session", None, json.dumps(payload), now, now, actual_user_id),
        )
        conn.commit()
        cur.close()
        conn.close()
    return get_session(sid, actual_user_id) or {"id": sid, "title": actual_title, "user_id": actual_user_id, **_empty_payload()}


def save_session(
    arg1: Any,
    arg2: dict[str, Any] | None = None,
    *,
    allow_insert: bool = True,
    preserve: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Update a session row. With allow_insert=False a missing row (deleted chat) is not re-created.

    `preserve` names fields (title or payload keys) that are re-read from the stored row inside the write's
    lock and copied into `session` first, so a background writer holding a stale copy cannot revert them."""
    init_ui_sessions()
    if arg2 is not None:
        user_id = str(arg1 or "anonymous")
        session = arg2
    else:
        session = arg1
        user_id = str(session.get("user_id") or "anonymous")

    sid = str(session.get("id") or "")
    if not sid:
        raise ValueError("session id required")
    now = _now()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        if preserve:
            cur.execute("SELECT * FROM ui_sessions WHERE id=?", (sid,))
            stored_row = cur.fetchone()
            if stored_row is not None:
                stored = _row_to_session(stored_row)
                for key in preserve:
                    if key in stored:
                        session[key] = stored[key]
        title = str(session.get("title") or "New session").strip() or "New session"
        job_id = session.get("job_id")
        payload = _empty_payload()
        for key in payload:
            if key in session:
                payload[key] = session[key]
        # Never re-own a row: a stale or hand-built dict naming another user must not overwrite someone's chat.
        cur.execute(
            """UPDATE ui_sessions SET title=?, job_id=?, payload_json=?, updated_at=?
               WHERE id=? AND user_id=?""",
            (title, job_id, json.dumps(payload), now, sid, user_id),
        )
        if cur.rowcount == 0:
            cur.execute("SELECT 1 FROM ui_sessions WHERE id=?", (sid,))
            if cur.fetchone() is not None:
                conn.rollback()
                cur.close()
                conn.close()
                raise PermissionError("session belongs to another user")
            if not allow_insert:
                conn.commit()
                cur.close()
                conn.close()
                return session
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


def update_session_fields(
    session_id: str, fields: dict[str, Any] | None = None, *, mutate: Any = None
) -> dict[str, Any] | None:
    """Change only some fields of a stored session, atomically: the row is read, `mutate(stored)` runs on the fresh copy
    and `fields` are set, then it is written back, all inside the write lock. Every other field stays as stored.

    For background writers (live events, run progress). Saving a whole session they had loaded earlier wrote back a stale
    copy: a row event that loaded the chat before the run's final save and wrote after it erased that save (the intent,
    schema, plans and the "Run complete" message). None when the session is gone (a deleted chat is never re-created)."""
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM ui_sessions WHERE id=?", (session_id,))
            row = cur.fetchone()
            if row is None:
                return None
            stored = _row_to_session(row)
            if mutate is not None:
                mutate(stored)
            stored.update(fields or {})
            payload = _empty_payload()
            for key in payload:
                if key in stored:
                    payload[key] = stored[key]
            cur.execute(
                "UPDATE ui_sessions SET job_id=?, payload_json=?, updated_at=? WHERE id=?",
                (stored.get("job_id"), json.dumps(payload), _now(), session_id),
            )
            conn.commit()
            return stored
        finally:
            cur.close()
            conn.close()


def _delete_session(session_id: str, user_id: str | None) -> bool:
    init_ui_sessions()
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        if user_id is None:
            cur.execute("DELETE FROM ui_sessions WHERE id=?", (session_id,))
        else:
            cur.execute("DELETE FROM ui_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        deleted = cur.rowcount > 0
        conn.commit()
        cur.close()
        conn.close()
    return deleted


def delete_session(session_id: str, user_id: str) -> bool:
    return _delete_session(session_id, _require_user(user_id))


def delete_session_internal(session_id: str) -> bool:
    """Delete by id alone. Tests and the owner's admin script only; no route may call this."""
    return _delete_session(session_id, None)
