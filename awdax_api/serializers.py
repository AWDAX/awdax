from __future__ import annotations

from typing import Any

from awdax_api.dataset_export import dataset_row_count
from reasoning import ScrapeIntent
from regulatory_strategy import intent_uses_regulatory_feed


def to_awdax_instance(sess: dict[str, Any], *, with_row_count: bool = True) -> dict[str, Any]:
    intent = sess.get("intent")
    goal = sess.get("goal") or ""
    if not goal and intent:
        goal = ScrapeIntent.from_dict(intent).topic or ""
    out = {
        "id": sess["id"],
        "title": sess.get("title") or "Untitled chat",
        "goal": goal,
        "archived": bool(sess.get("archived")),
        "live_enabled": bool(sess.get("keep_live")),
        "created_at": sess["created_at"],
        "updated_at": sess["updated_at"],
    }
    if with_row_count:
        out["dataset_row_count"] = dataset_row_count(sess)
    return out


def to_awdax_messages(sess: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for m in sess.get("messages") or []:
        out.append(
            {
                "id": str(m.get("id") or ""),
                "instance_id": sess["id"],
                "role": m.get("role") or "assistant",
                "content": m.get("content") or "",
                "created_at": m.get("created_at") or sess["updated_at"],
            }
        )
    return out


def to_awdax_live_state(sess: dict[str, Any]) -> dict[str, Any]:
    run = sess.get("awdax_run")
    rows_total = dataset_row_count(sess)
    if run and run.get("rows_total") is not None:
        rows_total = max(rows_total, int(run.get("rows_total") or 0))
    latest = None
    if run:
        latest = {
            "id": run.get("id"),
            "instance_id": sess["id"],
            "status": run.get("status") or "running",
            "phase": run.get("phase") or "queued",
            "detail": run.get("detail") or "",
            "rows_total": rows_total,
            "rows_added": int(run.get("rows_added") or 0),
            "updated_at": run.get("updated_at") or sess["updated_at"],
        }
    interval = 3600
    if sess.get("intent"):
        intent = ScrapeIntent.from_dict(sess["intent"])
        if intent_uses_regulatory_feed(intent):
            interval = 3600
    return {
        "enabled": bool(sess.get("keep_live")),
        "latest_run": latest,
        "interval_seconds": interval,
        "batch_seconds": 300,
        "next_cycle_at": None,
        "rows_total": rows_total,
    }
