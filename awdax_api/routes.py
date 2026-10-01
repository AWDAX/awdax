from __future__ import annotations

import json
import os

from flask import Blueprint, Response, jsonify, request, stream_with_context

from awdax_api.dataset_export import build_dashboard, build_dataset_table
from awdax_api.errors import detail_response
from awdax_api.orchestrator import is_running, start_run
from awdax_api.serializers import to_awdax_instance, to_awdax_live_state, to_awdax_messages
from awdax_api.session_store import append_message, load_instance_session, persist_session
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
from ui_sessions import create_session, delete_session, get_session, list_sessions, save_session

bp = Blueprint("awdax_api", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@bp.get("/ready")
def ready():
    return jsonify({"status": "ok"})


@bp.get("/api/instances")
def list_instances():
    uid = get_user_id(request)
    rows = []
    for meta in list_sessions(uid):
        full = get_session(meta["id"], uid)
        if not full:
            continue
        if full.get("archived"):
            continue
        rows.append(to_awdax_instance(full))
    return jsonify(rows)


@bp.post("/api/instances")
def create_instance():
    uid = get_user_id(request)
    body = request.get_json(silent=True) or {}
    title = str(body.get("title") or "Untitled chat").strip() or "Untitled chat"
    goal = str(body.get("goal") or "").strip()
    sess = create_session(user_id=uid, title=title)
    if goal:
        sess["goal"] = goal
        sess = save_session(uid, sess)
    return jsonify(to_awdax_instance(sess)), 201


@bp.get("/api/instances/<instance_id>")
def get_instance(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_instance(sess))


@bp.patch("/api/instances/<instance_id>")
def patch_instance(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    body = request.get_json(silent=True) or {}
    if "title" in body:
        sess["title"] = str(body.get("title") or sess.get("title"))
    if "archived" in body:
        sess["archived"] = bool(body.get("archived"))
    if "live_enabled" in body:
        enabled = bool(body.get("live_enabled"))
        sess["keep_live"] = enabled
        jid = sess.get("job_id")
        if not enabled and jid:
            universal_service.stop_live(jid)
    sess = persist_session(sess)
    return jsonify(to_awdax_instance(sess))


@bp.delete("/api/instances/<instance_id>")
def delete_instance(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    jid = sess.get("job_id")
    if jid:
        universal_service.stop_live(jid)
    delete_session(instance_id, get_user_id(request))
    return ("", 204)


@bp.get("/api/instances/<instance_id>/messages")
def get_messages(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_messages(sess))


@bp.post("/api/instances/<instance_id>/messages")
def post_message(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    if is_running(instance_id):
        return detail_response(409, "A run is already active for this instance")
    body = request.get_json(silent=True) or {}
    content = str(body.get("content") or "").strip()
    if not content:
        return detail_response(400, "content is required")
    append_message(sess, role="user", content=content)
    sess["goal"] = content
    sess["keep_live"] = True
    
    # Auto-rename chat to first prompt if still untitled
    current_title = str(sess.get("title") or "").strip()
    if not current_title or current_title in ("Untitled chat", "New session", "Session 1"):
        sess["title"] = content[:80].strip()

    if sess.get("job_id"):
        universal_service.clear_job_dataset(sess["job_id"])
    sess = persist_session(sess)
    max_pages = body.get("max_pages")
    mp = int(max_pages) if max_pages is not None else None
    try:
        start_run(instance_id, content, max_pages=mp)
    except RuntimeError as e:
        return detail_response(409, str(e))
    return jsonify(to_awdax_messages(load_instance_session(instance_id) or sess)), 201


@bp.get("/api/instances/<instance_id>/dataset")
def get_dataset(instance_id: str):
    sess = load_instance_session(instance_id)
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
    sess = load_instance_session(instance_id)
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
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_dashboard(sess))


@bp.get("/api/instances/<instance_id>/live")
def get_live(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(to_awdax_live_state(sess))


@bp.patch("/api/instances/<instance_id>/live")
def patch_live(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled"))
    sess["keep_live"] = enabled
    jid = sess.get("job_id")
    if jid and not enabled:
        universal_service.stop_live(jid)
    sess = persist_session(sess)
    return jsonify(to_awdax_live_state(sess))


@bp.get("/api/instances/<instance_id>/live/stream")
def live_stream(instance_id: str):
    sess = load_instance_session(instance_id)
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
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_sources_response(sess))


@bp.get("/api/instances/<instance_id>/dataset/stats")
def get_stats(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    return jsonify(build_dataset_stats(sess))


@bp.post("/api/instances/<instance_id>/dataset/rescore")
def post_rescore(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    try:
        return jsonify(rescore_dataset(sess))
    except RuntimeError as e:
        return detail_response(409, str(e))


@bp.get("/api/instances/<instance_id>/graph/parameters")
def get_graph_parameters(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    include_partial = request.args.get("include_partial", "false").lower() == "true"
    return jsonify(graph_parameters(sess, include_partial=include_partial))


@bp.get("/api/instances/<instance_id>/graph")
def get_graph(instance_id: str):
    sess = load_instance_session(instance_id)
    if not sess:
        return detail_response(404, "Instance not found")
    include_partial = request.args.get("include_partial", "false").lower() == "true"
    raw = request.args.get("parameters") or ""
    params = [p.strip() for p in raw.split(",") if p.strip()]
    return jsonify(graph_charts(sess, params, include_partial=include_partial))


def register_websocket(sock) -> None:
    @sock.route("/api/instances/<instance_id>/live/ws")
    def live_ws(ws, instance_id: str):
        sess = load_instance_session(instance_id)
        if not sess:
            ws.send(json.dumps({"type": "error", "detail": "Instance not found"}))
            return
        live_bridge.add_ws(instance_id, ws)
        try:
            ws.send(json.dumps(live_bridge.hello_payload(instance_id), default=str))
            sub = live_bridge.subscribe(instance_id)
            try:
                while True:
                    msg = sub.get()
                    ws.send(json.dumps(msg, default=str))
            finally:
                live_bridge.unsubscribe(instance_id, sub)
        finally:
            live_bridge.remove_ws(instance_id, ws)
