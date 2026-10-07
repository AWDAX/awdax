"""
Per-account API keys (`awx_...`): a way for scripts and Claude (MCP) to act as one account, with no browser sign-in.

Only a hash is stored; the key itself is shown once, when it is made. A key belongs to one user and can be read-only or
read+write. It can never create or revoke keys (see awdax_api/key_routes.py), so a leaked key cannot mint more.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import ui_sessions

PREFIX = "awx_"
SCOPES = ("read", "write")
MAX_ACTIVE_KEYS = 10
MAX_KEY_LENGTH = 100
TOUCH_EVERY = timedelta(minutes=1)

# DB file whose table has been created in this process (re-runs if ui_sessions.DB_PATH is repointed, e.g. in tests).
_initialized = None


class KeyLimitError(RuntimeError):
    """The account already has the maximum number of active keys."""


@dataclass(frozen=True)
class ResolvedKey:
    user_id: str
    scopes: frozenset
    key_id: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(key: str) -> str:
    return hashlib.sha256((os.getenv("API_KEY_PEPPER", "") + key).encode("utf-8")).hexdigest()


def _connect() -> sqlite3.Connection:
    global _initialized
    conn = ui_sessions._conn()
    if _initialized != ui_sessions.DB_PATH:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                scopes TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id)")
        conn.commit()
        _initialized = ui_sessions.DB_PATH
    return conn


def _public(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "prefix": row["prefix"],
        "scopes": json.loads(row["scopes"]),
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
    }


def normalize_scopes(scopes) -> list[str]:
    """['read'] or ['read', 'write']. Write implies read. Anything else is a ValueError."""
    if scopes is None:
        return ["read"]
    if not isinstance(scopes, (list, tuple)) or not scopes or not all(isinstance(s, str) and s in SCOPES for s in scopes):
        raise ValueError('scopes must be ["read"] or ["read", "write"]')
    return ["read", "write"] if "write" in scopes else ["read"]


def create_key(user_id: str, name: str = "", scopes=None) -> dict:
    """A new key for `user_id`. The result carries the plaintext `key`, which is never retrievable again."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id required")
    scope_list = normalize_scopes(scopes)
    label = " ".join(str(name or "").split())[:60] or "API key"
    key = PREFIX + secrets.token_urlsafe(32)
    row_id = uuid.uuid4().hex[:12]
    created = _now().isoformat()
    with ui_sessions._lock:
        conn = _connect()
        try:
            active = conn.execute("SELECT COUNT(*) FROM api_keys WHERE user_id=? AND revoked_at IS NULL", (user_id,)).fetchone()[0]
            if active >= MAX_ACTIVE_KEYS:
                raise KeyLimitError(f"You already have {MAX_ACTIVE_KEYS} active API keys. Revoke one first.")
            conn.execute(
                "INSERT INTO api_keys (id, user_id, name, prefix, key_hash, scopes, created_at) VALUES (?,?,?,?,?,?,?)",
                (row_id, user_id, label, key[: len(PREFIX) + 6], _hash(key), json.dumps(scope_list), created),
            )
            conn.commit()
        finally:
            conn.close()
    return {"id": row_id, "name": label, "prefix": key[: len(PREFIX) + 6], "scopes": scope_list, "created_at": created, "last_used_at": None, "key": key}


def list_keys(user_id: str) -> list[dict]:
    """The account's active keys, newest first. Never the key or its hash."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id required")
    with ui_sessions._lock:
        conn = _connect()
        try:
            rows = conn.execute("SELECT * FROM api_keys WHERE user_id=? AND revoked_at IS NULL ORDER BY created_at DESC", (user_id,)).fetchall()
        finally:
            conn.close()
    return [_public(r) for r in rows]


def revoke_key(user_id: str, key_id: str) -> bool:
    if not isinstance(user_id, str) or not user_id.strip():
        raise ValueError("user_id required")
    with ui_sessions._lock:
        conn = _connect()
        try:
            cur = conn.execute(
                "UPDATE api_keys SET revoked_at=? WHERE id=? AND user_id=? AND revoked_at IS NULL", (_now().isoformat(), key_id, user_id)
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def resolve_key(key: str) -> ResolvedKey | None:
    """Who a presented key acts as, or None when it is unknown, malformed or revoked."""
    if not isinstance(key, str) or not key.startswith(PREFIX) or len(key) > MAX_KEY_LENGTH:
        return None
    with ui_sessions._lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM api_keys WHERE key_hash=? AND revoked_at IS NULL", (_hash(key),)).fetchone()
            if row is None:
                return None
            now = _now()
            conn.execute(
                "UPDATE api_keys SET last_used_at=? WHERE id=? AND (last_used_at IS NULL OR last_used_at < ?)",
                (now.isoformat(), row["id"], (now - TOUCH_EVERY).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()
    return ResolvedKey(row["user_id"], frozenset(json.loads(row["scopes"])), row["id"])
