"""POST /api/ask: a question about a table the browser already holds (a chat's dataset or an uploaded file)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request

from ask_data import AskError, AskUnavailable, answer_question, fast_answer
from auth_helper import get_user_id
from awdax_api.dataset_export import build_dataset_table
from awdax_api.errors import detail_response
from awdax_api.routes import bp
from awdax_api.session_store import load_instance_session
from column_kinds import ask_payload, profile_table
from query_engine import describe, run_query

_KINDS = {"number", "money", "percent", "period", "category", "url", "text", "empty"}
MAX_BODY = 8 * 2**20
# Each question costs a model call (and maybe a sandboxed calculation): a per-user budget, in this process.
ASKS_PER_WINDOW = 20
WINDOW_S = 300
_recent: dict[str, deque[float]] = defaultdict(deque)
_recent_lock = threading.Lock()


def _over_budget(uid: str) -> bool:
    now = time.monotonic()
    with _recent_lock:
        q = _recent[uid]
        while q and now - q[0] > WINDOW_S:
            q.popleft()
        if len(q) >= ASKS_PER_WINDOW:
            return True
        q.append(now)
        return False


@bp.post("/api/ask")
def ask():
    uid = get_user_id(request)  # same identity rules as every other route (strict mode answers 401)
    request.max_content_length = MAX_BODY  # checked before the body is read, so a huge one is never parsed
    body = request.get_json(silent=True) or {}
    columns = body.get("columns")
    rows = body.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        return detail_response(400, "columns and rows are required")
    cols = []
    for c in columns:
        if not isinstance(c, dict) or type(c.get("index")) is not int or not isinstance(c.get("key"), str):
            return detail_response(400, "each column needs an index and a key")
        cols.append({
            "index": c["index"],
            "key": c["key"][:80],
            "label": str(c.get("label") or c["key"])[:80],
            "kind": c.get("kind") if c.get("kind") in _KINDS else "text",
            "unit": str(c.get("unit") or "")[:20],
        })
    if not all(isinstance(r, dict) for r in rows):
        return detail_response(400, "rows must be objects")
    question = str(body.get("question") or "")
    # A plain question is answered without the model, so it neither costs a model call nor counts against the budget.
    plain = fast_answer(question, cols)
    if plain:
        return jsonify(plain)
    if _over_budget(uid):
        return detail_response(429, "You've asked a lot in a few minutes. Try again shortly, or pick a suggested question.")
    try:
        return jsonify(answer_question(question, cols, rows))
    except AskUnavailable as e:
        return detail_response(503, str(e))
    except AskError as e:
        # A guardrail turning a plan down is an answer ("can't do that with this table"), not a failed request.
        return jsonify({"kind": "refuse", "reason": str(e)})


def _plan_answer(typed, plan: dict, source: str) -> dict:
    result = run_query(typed, plan)
    return {
        "kind": "answer",
        "source": source,
        "meaning": describe(typed, plan, result),
        "columns": result["columns"],
        "rows": result["rows"],
        "overall": result["overall"],
        "unit": result["unit"],
        "matched": result["matched"],
        "used": result["used"],
        "excluded_count": result["excluded_count"],
        "excluded": result["excluded"],
    }


@bp.post("/api/instances/<instance_id>/ask")
def ask_instance(instance_id: str):
    """A question about a chat's own table, answered by the server: exact figures for counts, sums, averages, rankings,
    groupings and heavier calculations. For scripts and Claude; the app asks about the table it already holds."""
    uid = get_user_id(request)
    sess = load_instance_session(instance_id, uid)
    if not sess:
        return detail_response(404, "Instance not found")
    request.max_content_length = 64 * 1024
    body = request.get_json(silent=True) or {}
    question = str(body.get("question") or "").strip()
    if not question or len(question) > 500:
        return detail_response(400, "Ask a question of up to 500 characters.")
    table = build_dataset_table(sess, limit=5000)
    if not table or not table.get("rows"):
        return jsonify({"kind": "refuse", "reason": "This chat has no data yet. Start a research run, or wait for it to finish."})
    typed = profile_table(table["columns"], table["rows"], table.get("column_labels"))
    cols, rows = ask_payload(typed)
    try:
        reply = fast_answer(question, cols)
        source = "fast"
        if reply is None:
            if _over_budget(uid):
                return detail_response(429, "You've asked a lot in a few minutes. Try again shortly.")
            reply = answer_question(question, cols, rows)
            source = "plan"
    except AskUnavailable as e:
        return detail_response(503, str(e))
    except AskError as e:
        return jsonify({"kind": "refuse", "reason": str(e)})
    if reply["kind"] == "query":
        return jsonify(_plan_answer(typed, reply["query"], source))
    if reply["kind"] == "computed":
        return jsonify({
            "kind": "answer", "source": "calculation", "meaning": reply["meaning"], "columns": reply["columns"], "rows": reply["rows"],
            "matched": typed.row_count, "used": typed.row_count,
        })
    return jsonify(reply)
