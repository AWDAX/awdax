from __future__ import annotations

import logging
import threading
import time
from typing import Any

from awdax_api.live_bridge import live_bridge
from awdax_api.pipeline_runner import InstanceDeleted, run_pipeline_for_session
from awdax_api.run_registry import (
    RunCancelled,
    RunLimitError,
    check_cancelled,
    dequeue,
    enqueue,
    is_cancelled,
    is_running,
    mark_stopped,
    pop_startable,
    queue_position,
    queued_ids,
    register_job,
    request_cancel,
    try_mark_running,
    unregister_job,
)
from awdax_api.run_report import format_discovery_report
from awdax_api.serializers import to_awdax_live_state
from awdax_api.session_store import (
    append_message,
    append_run_event,
    load_instance_session,
    persist_run_state,
    persist_session,
    set_awdax_run,
    update_instance,
)
from inspector import ScrapePlan
from regulatory_strategy import intent_uses_regulatory_feed
from reasoning import ScrapeIntent
from scraper import ScrapeJob, universal_service

logger = logging.getLogger(__name__)


def _on_progress(instance_id: str, phase: str, detail: str) -> None:
    check_cancelled(instance_id)  # paused or deleted: unwind the run here, at its next step

    def change(sess: dict[str, Any]) -> None:
        set_awdax_run(sess, phase=phase, detail=detail, status="running")
        append_run_event(sess, phase=phase, detail=detail)

    sess = update_instance(instance_id, change)
    if not sess:
        return
    live_bridge.notify_instance(instance_id, {"type": "run_event", "event": (sess.get("run_events") or [])[-1]})
    live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})


def _on_source(instance_id: str, source: dict[str, Any]) -> None:
    check_cancelled(instance_id)
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

    def change(sess: dict[str, Any]) -> None:
        current = [old for old in sess.get("discovery_sources") or [] if old.get("url") != item["url"]]
        sess["discovery_sources"] = [*current, item]

    if update_instance(instance_id, change) is None:
        return
    live_bridge.notify_instance(instance_id, {"type": "source", "source": item})


def _on_job(instance_id: str, job_id: str) -> None:
    register_job(instance_id, job_id)
    update_instance(instance_id, lambda sess: sess.update(job_id=job_id))


def _wait_regulatory(instance_id: str, timeout: float = 3600) -> None:
    from RegulatoryFeed import feed_service

    start = time.time()
    while feed_service.is_running and time.time() - start < timeout:
        time.sleep(1)
    time.sleep(0.5)


def _wait_universal_job(job_id: str, timeout: float = 3600, instance_id: str | None = None) -> None:
    """Wait for the scrape pass. A paused or deleted chat stops it: the scraper ends at its next source or row, and
    RunCancelled unwinds the run so its slot is freed."""
    start = time.time()
    cancelled_at: float | None = None
    while universal_service.is_job_running(job_id) and time.time() - start < timeout:
        if instance_id and cancelled_at is None and is_cancelled(instance_id):
            universal_service.cancel_job(job_id)
            universal_service.stop_live(job_id)
            cancelled_at = time.time()
        if cancelled_at is not None and time.time() - cancelled_at > 120:
            break  # a step that does not stop quickly is abandoned: its rows are no longer wanted
        time.sleep(1)
    time.sleep(0.5)
    if instance_id and is_cancelled(instance_id):
        raise RunCancelled(instance_id)


def _job_from_session(sess: dict[str, Any]) -> tuple[list[ScrapePlan], ScrapeJob]:
    intent = ScrapeIntent.from_dict(sess["intent"])
    plans = [ScrapePlan.from_dict(p) for p in sess["plans"]]
    job = ScrapeJob(
        job_id=sess["job_id"],
        intent=intent,
        plans=plans,
        plan=plans[0],
        table_schema=sess.get("table_schema"),
    )
    return plans, job


def resume_instance(instance_id: str, sess: dict[str, Any]) -> None:
    """Restart work when live mode is switched on and nothing is running (Resume / Retry)."""
    if is_running(instance_id):
        return
    if queue_position(instance_id) is not None:
        return  # already waiting for a slot
    job_id = sess.get("job_id")
    last_failed = (sess.get("awdax_run") or {}).get("status") in ("failed", "cancelled")
    if (sess.get("intent") or {}).get("pipeline") == "places" and not last_failed:
        # A finished Maps run is not re-run by the live switch: every search is a billed Google request.
        return
    if job_id and sess.get("plans") and sess.get("intent") and not last_failed:
        if not universal_service.is_job_live(job_id):
            plans, job = _job_from_session(sess)
            universal_service.start_live(plans, job)
        return
    goal = str(sess.get("goal") or "").strip()
    if not goal:
        return
    if not sess.get("messages"):
        append_message(sess, role="user", content=goal)
        persist_session(sess)
    try:
        submit_run(instance_id, goal)
    except RuntimeError:
        pass  # a run is already active for this chat


def _run_thread(instance_id: str, goal: str, max_pages: int | None, location_hint: dict[str, Any] | None = None) -> None:
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
        persist_run_state(sess)
        sess = run_pipeline_for_session(
            sess, goal, on_progress=_on_progress, on_source=_on_source, on_job=_on_job, max_pages=max_pages, location_hint=location_hint
        )
        intent = ScrapeIntent.from_dict(sess["intent"]) if sess.get("intent") else None
        job_id = sess.get("job_id")

        if intent and intent_uses_regulatory_feed(intent):
            _wait_regulatory(instance_id)
            from RegulatoryFeed import feed_service

            snap = [it.get("id") for it in feed_service.list_feed(limit=500) if it.get("id")]
            sess["regulatory_feed_snapshot_ids"] = snap
        elif job_id and sess.get("plans"):
            _wait_universal_job(job_id, instance_id=instance_id)
            _, job = _job_from_session(sess)
            universal_service.rebuild_merged_table(job)

        latest = load_instance_session(instance_id)
        if latest is None:
            # Chat was deleted mid-run: stop its live job and write nothing.
            jid = sess.get("job_id")
            if jid:
                universal_service.stop_live(jid)
            return
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
        persist_run_state(sess)
        live_bridge.notify_instance(instance_id, {"type": "batch_complete"})
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
    except InstanceDeleted:
        logger.info("Chat %s was deleted during its run", instance_id)
    except RunCancelled:
        logger.info("Run of chat %s was stopped (paused or deleted)", instance_id)
        jid = sess.get("job_id") if sess else None
        if jid:
            universal_service.cancel_job(jid)
            universal_service.stop_live(jid)
        _finish_paused(instance_id)
    except Exception as e:
        logger.exception("Orchestrator failed for %s", instance_id)
        sess = load_instance_session(instance_id) or sess
        append_message(sess, role="assistant", content=f"**Run failed:** {e}")
        set_awdax_run(sess, status="failed", phase="failed", detail=str(e))
        sess["run_active"] = False
        persist_run_state(sess)
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})
    finally:
        jid = sess.get("job_id") if sess else None
        unregister_job(instance_id, jid)
        mark_stopped(instance_id)
        dispatch_queued()  # the slot this run held goes to the next one waiting


def _finish_paused(instance_id: str) -> None:
    """A stopped run leaves a quiet "paused" state with the rows it had; nothing is posted into the chat."""

    def change(sess: dict[str, Any]) -> None:
        set_awdax_run(sess, status="cancelled", phase="cancelled", detail="Paused")
        sess["run_active"] = False

    sess = update_instance(instance_id, change)
    if sess:
        try:
            jid = sess.get("job_id")
            if jid and sess.get("plans") and sess.get("intent"):
                _, job = _job_from_session(sess)
                universal_service.rebuild_merged_table(job)  # so the rows read so far show in the table
        except Exception:  # noqa: BLE001 - the pause itself must not fail on a partial table
            logger.info("Partial table not built for %s", instance_id)
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})


def submit_run(instance_id: str, goal: str, *, max_pages: int | None = None, location_hint: dict[str, Any] | None = None) -> str:
    """Start a run now, or put it on the waiting list when the server is at its limit. "started" or "queued".
    Raises RunLimitError only when the waiting list itself is full, and RuntimeError when this chat already has a run."""
    payload = {"goal": goal, "max_pages": max_pages, "location_hint": location_hint}
    try:
        start_run(instance_id, goal, max_pages=max_pages, location_hint=location_hint)
        dequeue(instance_id)
        return "started"
    except RunLimitError:
        sess = load_instance_session(instance_id)
        place = enqueue(instance_id, (sess or {}).get("user_id"), payload)  # RunLimitError here = list full
    _mark_queued(instance_id, place)
    return "queued"


def _mark_queued(instance_id: str, place: int | None = None) -> None:
    place = place or queue_position(instance_id) or 1

    def change(sess: dict[str, Any]) -> None:
        set_awdax_run(sess, status="running", phase="queued", detail=f"Waiting for a free slot (place {place} in line)")
        append_run_event(sess, phase="queued", detail=f"Waiting for a free slot (place {place} in line)")
        sess["run_active"] = True

    sess = update_instance(instance_id, change)
    if sess:
        live_bridge.notify_instance(instance_id, {"type": "status", "state": to_awdax_live_state(sess)})


def dispatch_queued() -> int:
    """Start waiting runs while there is room for them (a slot just freed, or limits were raised). Returns how many started."""
    started = 0
    while True:
        item = pop_startable()
        if item is None:
            break
        instance_id, user_id, payload = item
        if load_instance_session(instance_id) is None:  # deleted while waiting
            continue
        try:
            start_run(instance_id, payload["goal"], max_pages=payload.get("max_pages"), location_hint=payload.get("location_hint"))
            started += 1
        except RunLimitError:
            enqueue(instance_id, user_id, payload, front=True)  # lost the slot to a request that came in just now
            break
        except RuntimeError:
            continue  # already running
    for n, iid in enumerate(queued_ids(), start=1):
        _mark_queued(iid, n)  # places in line moved up
    return started


def cancel_run(instance_id: str) -> str:
    """Stop this chat's work for a pause or a delete: leave the waiting list, or stop the active run at its next step.
    "queued" (it was waiting), "running" (told to stop) or "idle"."""
    if dequeue(instance_id):
        update_instance(instance_id, lambda sess: (set_awdax_run(sess, status="cancelled", phase="cancelled", detail="Paused"), sess.update(run_active=False)))
        return "queued"
    return "running" if request_cancel(instance_id) else "idle"


def recover_interrupted_runs() -> int:
    """At startup no run thread exists yet, so any session still marked running was cut off by a restart.
    Mark it failed with a clear message; otherwise the chat shows "running" forever."""
    from ui_sessions import list_all_sessions_internal

    fixed = 0
    for meta in list_all_sessions_internal():
        sess = load_instance_session(meta["id"])
        if not sess:
            continue
        run = sess.get("awdax_run") or {}
        if not sess.get("run_active") and run.get("status") != "running":
            continue
        detail = "The server restarted during this run. Send the request again to retry."
        append_message(sess, role="assistant", content=f"**Run interrupted.** {detail}")
        set_awdax_run(sess, status="failed", phase="failed", detail=detail)
        sess["run_active"] = False
        persist_session(sess)
        fixed += 1
    if fixed:
        logger.info("Marked %d interrupted run(s) as failed", fixed)
    return fixed


def start_run(instance_id: str, goal: str, *, max_pages: int | None = None, location_hint: dict[str, Any] | None = None) -> None:
    if is_running(instance_id):
        raise RuntimeError("A run is already active for this instance")
    sess = load_instance_session(instance_id)
    try_mark_running(instance_id, (sess or {}).get("user_id"))
    try:
        t = threading.Thread(target=_run_thread, args=(instance_id, goal, max_pages, location_hint), daemon=True, name=f"awdax-run-{instance_id[:8]}")
        t.start()
    except BaseException:
        mark_stopped(instance_id)
        raise
