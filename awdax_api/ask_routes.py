"""POST /api/ask: a question about a table the browser already holds (a chat's dataset or an uploaded file)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request

from ask_data import AskError, AskUnavailable, answer_question
from auth_helper import get_user_id
from awdax_api.errors import detail_response
from awdax_api.routes import bp

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
    if _over_budget(uid):
        return detail_response(429, "You've asked a lot in a few minutes. Try again shortly, or pick a suggested question.")
    try:
        return jsonify(answer_question(str(body.get("question") or ""), cols, rows))
    except AskUnavailable as e:
        return detail_response(503, str(e))
    except AskError as e:
        # A guardrail turning a plan down is an answer ("can't do that with this table"), not a failed request.
        return jsonify({"kind": "refuse", "reason": str(e)})
