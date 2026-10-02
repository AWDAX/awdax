"""Helpers for Awdax instance fields stored in ui_sessions payload."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ui_sessions import get_session, save_session


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_awdax_defaults(sess: dict[str, Any]) -> dict[str, Any]:
    sess.setdefault("messages", [])
    sess.setdefault("goal", "")
    sess.setdefault("archived", False)
    sess.setdefault("run_events", [])
    sess.setdefault("discovery_sources", [])
    sess.setdefault("run_active", False)
    sess.setdefault("regulatory_feed_snapshot_ids", [])
    if sess.get("awdax_run") is None:
        sess["awdax_run"] = None
    return sess


def load_instance_session(instance_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    sess = get_session(instance_id, user_id)
    if not sess:
        return None
    return ensure_awdax_defaults(sess)


def persist_session(sess: dict[str, Any]) -> dict[str, Any]:
    ensure_awdax_defaults(sess)
    return save_session(sess, allow_insert=False)


def append_message(sess: dict[str, Any], *, role: str, content: str) -> dict[str, Any]:
    msgs = list(sess.get("messages") or [])
    msgs.append(
        {
            "id": uuid.uuid4().hex,
            "instance_id": sess["id"],
            "role": role,
            "content": content,
            "created_at": _now(),
        }
    )
    sess["messages"] = msgs
    return sess


def set_awdax_run(
    sess: dict[str, Any],
    *,
    run_id: str | None = None,
    status: str = "running",
    phase: str = "queued",
    detail: str = "",
    rows_total: int | None = None,
    rows_added: int | None = None,
) -> dict[str, Any]:
    prev = dict(sess.get("awdax_run") or {})
    run = {
        "id": run_id or prev.get("id") or uuid.uuid4().hex[:16],
        "instance_id": sess["id"],
        "status": status,
        "phase": phase,
        "detail": detail,
        "rows_total": rows_total if rows_total is not None else prev.get("rows_total", 0),
        "rows_added": rows_added if rows_added is not None else prev.get("rows_added", 0),
        "updated_at": _now(),
    }
    sess["awdax_run"] = run
    return sess


def append_run_event(sess: dict[str, Any], *, phase: str, detail: str) -> dict[str, Any]:
    events = list(sess.get("run_events") or [])
    eid = int(events[-1]["id"]) + 1 if events else 1
    events.append({"id": eid, "run_id": (sess.get("awdax_run") or {}).get("id", ""), "phase": phase, "detail": detail, "created_at": _now()})
    sess["run_events"] = events[-50:]
    return sess
