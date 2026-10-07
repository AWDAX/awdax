from __future__ import annotations

import json
import queue
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context

from awdax_api.dataset_export import build_dashboard, build_dataset_table
from awdax_api.errors import detail_response
from awdax_api.orchestrator import cancel_run, is_running, resume_instance, submit_run
from awdax_api.run_registry import RunLimitError, has_room
from awdax_api.serializers import to_awdax_instance, to_awdax_live_state, to_awdax_messages
from awdax_api.session_store import append_message, ensure_awdax_defaults, load_instance_session, persist_session
from awdax_api.sources_stats_graph import (
    build_dataset_stats,
    build_sources_response,
    graph_charts,
    graph_parameters,
    rescore_dataset,
)
from awdax_api.live_bridge import live_bridge
from auth_helper import get_user_id
from scraper import universal_service
from ui_sessions import create_session, delete_session, list_full_sessions, save_session

bp = Blueprint("awdax_api", __name__)

MAX_PROMPT_CHARS = 2000
MAX_PAGES_LIMIT = 10
PROMPT_TOO_LONG = f"Request is too long ({MAX_PROMPT_CHARS} characters max)"
WS_KEEPALIVE_SECONDS = 15
RUNS_BUSY = "Too many runs are active right now. Please try again in a few minutes."


def _pump(sub, send, timeout: float = WS_KEEPALIVE_SECONDS) -> None:
    """Forward queued live messages to `send`. On an idle timeout send a ping frame; a send on a closed
    socket raises, which ends the loop so the caller's cleanup runs."""
    while True:
        try:
            msg = sub.get(timeout=timeout)
        except queue.Empty:
            send(json.dumps({"type": "ping"}))
            continue
        send(json.dumps(msg, default=str))


def _coordinate(value: Any, limit: float) -> float:
    if isinstance(value, bool):
        raise ValueError
    number = float(value)
    if not -limit <= number <= limit:  # also false for NaN
        raise ValueError
    return number


def _location_hint(body: dict[str, Any]) -> dict[str, Any] | None:
    """Where the user is, for a "near me" search: the position the browser sent with the message. Nothing else is trusted
    (a header could be typed by anyone); with no position the search falls back to PLACES_DEFAULT_CENTER."""
    raw = body.get("location")
    if raw is None:
        return None
    try:
        if not isinstance(raw, dict):
            raise ValueError
        return {"lat": _coordinate(raw.get("lat"), 90), "lng": _coordinate(raw.get("lng"), 180), "source": "browser"}
    except (TypeError, ValueError):
        raise ValueError("location must be {lat, lng} in degrees") from None


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/ready")
def ready():
    return jsonify({"status": "ok"})


@bp.get("/api/instances")
def list_instances():
    uid = get_user_id(request)
    # One query for the whole list (it used to read the table once for the list and once more per chat).
    rows = [to_awdax_instance(ensure_awdax_defaults(full), with_row_count=False) for full in list_full_sessions(uid) if not full.get("archived")]
    return jsonify(rows)


@bp.post("/api/instances")
def create_instance():
    uid = get_user_id(request)
    body = request.get_json(silent=True) or {}
    title = str(body.get("title") or "Untitled chat")[:80].strip() or "Untitled chat"
    goal = str(body.get("goal") or "").strip()
    if len(goal) > MAX_PROMPT_CHARS:
        return detail_response(400, PROMPT_TOO_LONG)
    sess = create_session(user_id=uid, title=title)
    if goal:
        sess["goal"] = goal
        sess = save_session(uid, sess)
    return jsonify(to_awdax_instance(sess)), 201


@bp.get("/api/instances/<instance_id>")
def get_instance(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_instance(sess))


@bp.patch("/api/instances/<instance_id>")
def patch_instance(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    body = request.get_json(silent=True) or {}
    if "title" in body:
        sess["title"] = str(body.get("title") or "").strip()[:80] or sess.get("title")
    if "archived" in body:
        sess["archived"] = bool(body.get("archived"))
    if "live_enabled" in body:
        enabled = bool(body.get("live_enabled"))
        sess["keep_live"] = enabled
        jid = sess.get("job_id")
        if not enabled and jid:
            universal_service.stop_live(jid)
    sess = persist_session(sess)
    if body.get("live_enabled"):
        resume_instance(instance_id, sess)
        sess = load_instance_session(instance_id) or sess
    return jsonify(to_awdax_instance(sess))


@bp.delete("/api/instances/<instance_id>")
def delete_instance(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    jid = sess.get("job_id")
    if jid:
        universal_service.stop_live(jid)
    cancel_run(instance_id)  # an active run stops at its next step and frees its slot; a waiting one leaves the list
    delete_session(instance_id, get_user_id(request))
    return ("", 204)


@bp.get("/api/instances/<instance_id>/messages")
def get_messages(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_messages(sess))


@bp.post("/api/instances/<instance_id>/messages")
def post_message(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    if is_running(instance_id):
        return detail_response(409, "A run is already active for this instance")
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "").strip()
    if not content:
        return detail_response(400, "content is required")
    if len(content) > MAX_PROMPT_CHARS:
        return detail_response(400, PROMPT_TOO_LONG)
    mp = None
    if body.get("max_pages") is not None:
        try:
            mp = int(body["max_pages"])
        except (TypeError, ValueError, OverflowError):
            return detail_response(400, "max_pages must be a whole number")
        mp = max(1, min(mp, MAX_PAGES_LIMIT))
    try:
        hint = _location_hint(body)
    except ValueError as exc:
        return detail_response(400, str(exc))
    # Refuse before any side effect: a request turned away must not stop tracking, clear the dataset or save a message.
    # At the run limit a request waits for a slot; only a full waiting list turns it away.
    if not has_room(instance_id, sess.get("user_id")):
        return detail_response(429, RUNS_BUSY)
    append_message(sess, role="user", content=content)
    sess["goal"] = content
    sess["keep_live"] = True
    
    # Auto-rename chat to first prompt if still untitled
    current_title = str(sess.get("title") or "").strip()
    if not current_title or current_title in ("Untitled chat", "New session", "Session 1"):
        sess["title"] = content[:80].strip()

    if sess.get("job_id"):
        # The new run gets a new job id; stop the old live loop or it keeps re-scraping unseen (no-op if not live).
        universal_service.stop_live(sess["job_id"])
        universal_service.clear_job_dataset(sess["job_id"])
    sess = persist_session(sess)
    start_kwargs: dict[str, Any] = {"max_pages": mp}
    if hint:
        start_kwargs["location_hint"] = hint
    try:
        submit_run(instance_id, content, **start_kwargs)
    except RunLimitError:
        return detail_response(429, RUNS_BUSY)
    except RuntimeError as e:
        return detail_response(409, str(e))
    return jsonify(to_awdax_messages(load_instance_session(instance_id, get_user_id(request)) or sess)), 201


@bp.get("/api/instances/<instance_id>/dataset")
def get_dataset(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    try:
        limit = min(int(request.args.get("limit", "5000")), 5000)
    except ValueError:
        limit = 5000
    include_partial = request.args.get("include_partial", "false").lower() == "true"
    table = build_dataset_table(sess, limit=limit, include_partial=include_partial)
    if not table:
        return jsonify({"columns": [], "rows": [], "row_count": 0, "records": []})
    return jsonify(table)


@bp.delete("/api/instances/<instance_id>/dataset")
def delete_dataset(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    if is_running(instance_id):
        return detail_response(409, "Run in progress")
    jid = sess.get("job_id")
    if jid:
        universal_service.clear_job_dataset(jid)
    sess["regulatory_feed_snapshot_ids"] = []
    persist_session(sess)
    return ("", 204)


@bp.get("/api/instances/<instance_id>/dashboard")
def get_dashboard(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_dashboard(sess))


@bp.get("/api/instances/<instance_id>/live")
def get_live(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_live_state(sess))


@bp.patch("/api/instances/<instance_id>/live")
def patch_live(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled"))
    sess["keep_live"] = enabled
    jid = sess.get("job_id")
    if jid and not enabled:
        universal_service.stop_live(jid)
    sess = persist_session(sess)
    if not enabled:
        # Pausing stops an active first pass too (it used to run on and keep its slot) and leaves the waiting list.
        cancel_run(instance_id)
        sess = load_instance_session(instance_id) or sess
    if enabled:
        resume_instance(instance_id, sess)
        sess = load_instance_session(instance_id) or sess
    return jsonify(to_awdax_live_state(sess))


@bp.get("/api/instances/<instance_id>/live/stream")
def live_stream(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")

    @stream_with_context
    def generate():
        sub = live_bridge.subscribe(instance_id)
        try:
            hello = live_bridge.hello_payload(instance_id)
            yield f"event: status\ndata: {json.dumps(hello.get('state'), default=str)}\n\n"
            while True:
                try:
                    msg = sub.get(timeout=15)
                    etype = msg.get("type", "message")
                    if etype == "run_event":
                        yield f"event: run_event\ndata: {json.dumps(msg.get('event'), default=str)}\n\n"
                    elif etype == "source":
                        yield f"event: source\ndata: {json.dumps(msg.get('source'), default=str)}\n\n"
                    elif etype == "status":
                        yield f"event: status\ndata: {json.dumps(msg.get('state'), default=str)}\n\n"
                    else:
                        yield f"data: {json.dumps(msg, default=str)}\n\n"
                except Exception:
                    yield ": keepalive\n\n"
        finally:
            live_bridge.unsubscribe(instance_id, sub)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@bp.get("/api/instances/<instance_id>/sources")
def get_sources(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_sources_response(sess))


@bp.get("/api/instances/<instance_id>/failed-links")
def get_failed_links(instance_id: str):
    """The links this chat's run could not read with a plain web request (blocked, not found, unreachable, CAPTCHA), as a
    table, plus the websites the research step ranked."""
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    from url_access import dataset_for_job

    table = dataset_for_job(str(sess.get("job_id") or ""))
    research = sess.get("research") or {}
    return jsonify({**table, "research": research.get("websites") or []})


@bp.get("/api/instances/<instance_id>/dataset/stats")
def get_stats(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_dataset_stats(sess))


@bp.post("/api/instances/<instance_id>/dataset/rescore")
def post_rescore(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    try:
        return jsonify(rescore_dataset(sess))
    except RuntimeError as e:
        return detail_response(409, str(e))


@bp.get("/api/instances/<instance_id>/graph/parameters")
def get_graph_parameters(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    include_partial = request.args.get("include_partial", "false").lower() == "true"
    return jsonify(graph_parameters(sess, include_partial=include_partial))


@bp.get("/api/instances/<instance_id>/graph")
def get_graph(instance_id: str):
    sess = load_instance_session(instance_id, get_user_id(request))
    if not sess:
        return detail_response(404, "Instance not found")
    include_partial = request.args.get("include_partial", "false").lower() == "true"
    raw = request.args.get("parameters") or ""
    params = [p.strip() for p in raw.split(",") if p.strip()]
    return jsonify(graph_charts(sess, params, include_partial=include_partial))


def register_websocket(sock) -> None:
    @sock.route("/api/instances/<instance_id>/live/ws")
    def live_ws(ws, instance_id: str):
        sess = load_instance_session(instance_id, get_user_id(request))
        if not sess:
            ws.send(json.dumps({"type": "error", "detail": "Instance not found"}))
            return
        live_bridge.add_ws(instance_id, ws)
        try:
            ws.send(json.dumps(live_bridge.hello_payload(instance_id), default=str))
            sub = live_bridge.subscribe(instance_id)
            try:
                _pump(sub, ws.send)
            finally:
                live_bridge.unsubscribe(instance_id, sub)
        finally:
            live_bridge.remove_ws(instance_id, ws)
