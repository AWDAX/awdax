"""
API-key management (/api/keys) and the policy every request passes through: who is calling, and what that caller may do.

A key can read, or read and write, as its account. It can never manage keys (only a signed-in session can), so a leaked
key cannot mint or revoke others. Calls made with a key are rate limited per key.
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque

from flask import jsonify, request

import api_keys
from auth_helper import get_identity, get_user_id
from awdax_api.errors import detail_response
from awdax_api.routes import bp

PUBLIC_PATHS = frozenset({"/health", "/ready", "/api/openapi.json"})
# POSTs that only read or compute, so a read-only key may use them. /api/mcp carries every MCP call: the tools it runs make
# their own API calls with the same key, and those are held to its scopes one by one.
READ_ONLY_POSTS = re.compile(r"^/api/(?:mcp|ask)$|^/api/instances/[^/]+/ask$")
KEY_REQUESTS_PER_WINDOW = 120
KEY_WINDOW_S = 60
_recent: dict[str, deque[float]] = defaultdict(deque)
_recent_lock = threading.Lock()


def _over_key_budget(key_id: str) -> bool:
    now = time.monotonic()
    with _recent_lock:
        q = _recent[key_id]
        while q and now - q[0] > KEY_WINDOW_S:
            q.popleft()
        if len(q) >= KEY_REQUESTS_PER_WINDOW:
            return True
        q.append(now)
        return False


@bp.before_request
def _who_and_what():
    """Every route but the public ones needs a proven identity; a key is held to its scopes and its rate limit."""
    if request.path in PUBLIC_PATHS or request.method == "OPTIONS":
        return None
    identity = get_identity(request)  # raises AuthError (401) when the caller cannot be proven
    if identity.method != "api_key":
        return None
    if request.path.startswith("/api/keys"):
        return detail_response(403, "API keys cannot manage API keys. Sign in to the app to do that.")
    if request.method not in ("GET", "HEAD") and "write" not in identity.scopes and not READ_ONLY_POSTS.match(request.path):
        return detail_response(403, "This API key is read-only.")
    if _over_key_budget(identity.key_id):
        return detail_response(429, f"Too many requests for this API key (limit {KEY_REQUESTS_PER_WINDOW} a minute). Slow down.")
    return None


@bp.get("/api/me")
def whoami():
    identity = get_identity(request)
    return jsonify({"user_id": identity.user_id, "auth": identity.method, "scopes": sorted(identity.scopes)})


@bp.get("/api/keys")
def list_api_keys():
    return jsonify(api_keys.list_keys(get_user_id(request)))


@bp.post("/api/keys")
def create_api_key():
    uid = get_user_id(request)
    body = request.get_json(silent=True) or {}
    try:
        created = api_keys.create_key(uid, str(body.get("name") or ""), body.get("scopes"))
    except ValueError as exc:
        return detail_response(400, str(exc))
    except api_keys.KeyLimitError as exc:
        return detail_response(409, str(exc))
    return jsonify(created), 201


@bp.delete("/api/keys/<key_id>")
def revoke_api_key(key_id: str):
    if not api_keys.revoke_key(get_user_id(request), key_id):
        return detail_response(404, "Key not found")
    return ("", 204)
