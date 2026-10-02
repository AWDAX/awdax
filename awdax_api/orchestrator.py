from __future__ import annotations

import logging
import threading
import time
from typing import Any

from awdax_api.live_bridge import live_bridge
from awdax_api.pipeline_runner import run_pipeline_for_session
from awdax_api.run_registry import (
    is_running,
    mark_running,
    mark_stopped,
    register_job,
    unregister_job,
)
from awdax_api.run_report import format_discovery_report
from awdax_api.serializers import to_awdax_live_state
from awdax_api.session_store import (
    append_message,
    append_run_event,
    load_instance_session,
    persist_session,
    set_awdax_run,
)
from inspector import ScrapePlan
from regulatory_strategy import intent_uses_regulatory_feed
from reasoning import ScrapeIntent
from scraper import ScrapeJob, universal_service

logger = logging.getLogger(__name__)


def _on_progress(instance_id: str, phase: str, detail: str) -> None:
    sess = load_instance_session(instance_id)
    if not sess:
        return
    set_awdax_run(sess, phase=phase, detail=detail, status="running")
    append_run_event(sess, phase=phase, detail=detail)
    persist_session(sess)
    live_bridge.notify_instance(instance_id, {"type": "run_event", "event": (sess.get("run_events") or [])[-1]})
    live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})


def _on_source(instance_id: str, source: dict[str, Any]) -> None:
    sess = load_instance_session(instance_id)
    if not sess:
        return
    item = {
        "id": source["url"],
        "url": source["url"],
        "title": source.get("title") or source["url"],
        "status": source.get("status") or "selected",
        "accepted": 0,
        "partial": 0,
        "rejected": 0,
        "reason": source.get("reason") or "",
        "domain": source.get("domain") or "",
        "origin": source.get("origin") or "search",
        "rank_score": source.get("rank_score"),
        "rank_reasons": [],
        "deep_accepted": 0,
        "deep_notes": [],
        "linked_from": None,
    }
    current = [old for old in sess.get("discovery_sources") or [] if old.get("url") != item["url"]]
    sess["discovery_sources"] = [*current, item]
    persist_session(sess)
    live_bridge.notify_instance(instance_id, {"type": "source", "source": item})


def _on_job(instance_id: str, job_id: str) -> None:
    register_job(instance_id, job_id)
    live_bridge.register_job(instance_id, job_id)
    sess = load_instance_session(instance_id)
    if sess:
        sess["job_id"] = job_id
        persist_session(sess)


def _wait_regulatory(instance_id: str, timeout: float = 3600) -> None:
    from RegulatoryFeed import feed_service

    start = time.time()
    while feed_service.is_running and time.time() - start < timeout:
        time.sleep(1)
    time.sleep(0.5)


def _wait_universal_job(job_id: str, timeout: float = 3600) -> None:
    start = time.time()
    while universal_service.is_job_running(job_id) and time.time() - start < timeout:
        time.sleep(1)
    time.sleep(0.5)


def _run_thread(instance_id: str, goal: str, max_pages: int | None) -> None:
    sess = load_instance_session(instance_id)
    if not sess:
        return
    try:
        sess["discovery_sources"] = []
        sess["sources"] = []
        sess["plans"] = []
        sess["run_events"] = []
        sess["awdax_run"] = None
        set_awdax_run(sess, status="running", phase="queued", detail="Starting…", rows_total=0, rows_added=0)
        sess["run_active"] = True
        persist_session(sess)
        sess = run_pipeline_for_session(sess, goal, on_progress=_on_progress, on_source=_on_source, on_job=_on_job, max_pages=max_pages)
        intent = ScrapeIntent.from_dict(sess["intent"]) if sess.get("intent") else None
        job_id = sess.get("job_id")

        if intent and intent_uses_regulatory_feed(intent):
            _wait_regulatory(instance_id)
            from RegulatoryFeed import feed_service

            snap = [it.get("id") for it in feed_service.list_feed(limit=500) if it.get("id")]
            sess["regulatory_feed_snapshot_ids"] = snap
        elif job_id and sess.get("plans"):
            _wait_universal_job(job_id)
            intent = ScrapeIntent.from_dict(sess["intent"])
            plans = [ScrapePlan.from_dict(p) for p in sess["plans"]]
            job = ScrapeJob(
                job_id=job_id,
                intent=intent,
                plans=plans,
                plan=plans[0],
                table_schema=sess.get("table_schema"),
            )
            universal_service.rebuild_merged_table(job)

        latest = load_instance_session(instance_id)
        if latest:
            for key in ("messages", "run_events", "awdax_run", "discovery_sources", "title", "archived", "keep_live"):
                sess[key] = latest.get(key)
        report = format_discovery_report(sess, goal=goal)
        summary = f"**Run complete.**\n\n{report}"
        append_message(sess, role="assistant", content=summary)
        from awdax_api.dataset_export import dataset_row_count

        rows = dataset_row_count(sess)
        set_awdax_run(
            sess,
            status="succeeded",
            phase="complete",
            detail="First pass complete",
            rows_total=rows,
            rows_added=rows,
        )
        sess["run_active"] = False
        persist_session(sess)
        live_bridge.notify_instance(instance_id, {"type": "batch_complete"})
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
    except Exception as e:
        logger.exception("Orchestrator failed for %s", instance_id)
        sess = load_instance_session(instance_id) or sess
        append_message(sess, role="assistant", content=f"**Run failed:** {e}")
        set_awdax_run(sess, status="failed", phase="failed", detail=str(e))
        sess["run_active"] = False
        persist_session(sess)
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
    finally:
        jid = sess.get("job_id") if sess else None
        unregister_job(instance_id, jid)
        mark_stopped(instance_id)


def start_run(instance_id: str, goal: str, *, max_pages: int | None = None) -> None:
    if is_running(instance_id):
        raise RuntimeError("A run is already active for this instance")
    mark_running(instance_id)
    t = threading.Thread(target=_run_thread, args=(instance_id, goal, max_pages), daemon=True, name=f"awdax-run-{instance_id[:8]}")
    t.start()
