"""Live updates for one chat: the event stream (SSE) and the WebSocket, both capped per chat and per user."""

from __future__ import annotations

import json
import queue

from flask import Response, request, stream_with_context

from auth_helper import get_user_id
from awdax_api.errors import detail_response
from awdax_api.live_bridge import live_bridge
from awdax_api.routes import bp
from awdax_api.session_store import load_instance_session

WS_KEEPALIVE_SECONDS = 15
TOO_MANY_STREAMS = "This chat is open in too many tabs. Close a few and reload."


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


@bp.get("/api/instances/<instance_id>/live/stream")
def live_stream(instance_id: str):
    uid = get_user_id(request)
    sess = load_instance_session(instance_id, uid)
    if not sess:
        return detail_response(404, "Instance not found")
    sub = live_bridge.subscribe(instance_id, owner=uid)
    if sub is None:
        return detail_response(429, TOO_MANY_STREAMS)

    @stream_with_context
    def generate():
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

    resp = Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
    # Also when the client leaves before the stream starts (then the generator's finally never runs).
    resp.call_on_close(lambda: live_bridge.unsubscribe(instance_id, sub))
    return resp


def register_websocket(sock) -> None:
    @sock.route("/api/instances/<instance_id>/live/ws")
    def live_ws(ws, instance_id: str):
        uid = get_user_id(request)
        sess = load_instance_session(instance_id, uid)
        if not sess:
            ws.send(json.dumps({"type": "error", "detail": "Instance not found"}))
            return
        sub = live_bridge.subscribe(instance_id, owner=uid)
        if sub is None:
            ws.send(json.dumps({"type": "error", "detail": TOO_MANY_STREAMS}))
            return
        live_bridge.add_ws(instance_id, ws)
        try:
            ws.send(json.dumps(live_bridge.hello_payload(instance_id), default=str))
            _pump(sub, ws.send)
        finally:
            live_bridge.unsubscribe(instance_id, sub)
            live_bridge.remove_ws(instance_id, ws)
