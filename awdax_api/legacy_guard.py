"""Keep the pre-React API in app.py (/api/sessions*, /api/feed, /api/events, /api/scrape/*, ...) off the network.

Those routes predate per-user ownership checks, so any signed-in caller could read or stop another user's job.
By default every path outside the React API is answered with the standard JSON 404. Set AWDAX_LEGACY_API=1
(or true) to bring the old UI back for local use.
"""
from __future__ import annotations

import os

from flask import request

from awdax_api.errors import detail_response

# Exact paths, plus anything under these prefixes ("/api/instances/<id>/live/ws" and ".../live/stream" included).
ALLOWED_EXACT = frozenset({"/health", "/ready", "/api/instances"})
ALLOWED_PREFIXES = ("/api/instances/",)


def legacy_enabled() -> bool:
    return os.getenv("AWDAX_LEGACY_API", "").strip().lower() in {"1", "true"}


def _allowed(path: str) -> bool:
    return path in ALLOWED_EXACT or path.startswith(ALLOWED_PREFIXES)


def install(app) -> None:
    @app.before_request
    def _block_legacy_routes():
        # Preflight stays as it is today; it carries no data and the real request is checked on its own.
        if request.method == "OPTIONS" or _allowed(request.path) or legacy_enabled():
            return None
        return detail_response(404, "Not found")
