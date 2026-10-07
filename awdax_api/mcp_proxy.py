"""
/api/mcp: the MCP endpoint at the site's own address.

The MCP server (mcp_server/, `python -m mcp_server`) runs beside the API on 127.0.0.1. This route hands each request to it,
so Claude connects to https://<site>/api/mcp through the same proxy and tunnel as everything else, with the same API key.
The identity check in key_routes.py already ran: only a request that carries a working credential gets this far.
"""

from __future__ import annotations

import os

import requests
from flask import Response, request

from awdax_api.errors import detail_response
from awdax_api.routes import bp

FORWARD = ("Authorization", "X-API-Key", "Content-Type", "Accept", "MCP-Protocol-Version", "Mcp-Session-Id")
PASS_BACK = ("Content-Type", "Mcp-Session-Id", "WWW-Authenticate")
MAX_BODY = 1_000_000
TIMEOUT_S = 120


def upstream() -> str:
    return (os.getenv("MCP_UPSTREAM") or f"http://127.0.0.1:{os.getenv('MCP_PORT', '8001')}").rstrip("/") + "/mcp"


@bp.route("/api/mcp", methods=["GET", "POST", "DELETE"])
def mcp_gateway():
    if (request.content_length or 0) > MAX_BODY:
        return detail_response(413, "Request too large")
    headers = {name: request.headers[name] for name in FORWARD if request.headers.get(name)}
    try:
        res = requests.request(request.method, upstream(), data=request.get_data(), headers=headers, timeout=TIMEOUT_S)
    except requests.RequestException:
        return detail_response(503, "The MCP service is not running. Start it with `python -m mcp_server`.")
    return Response(res.content, status=res.status_code, headers={name: res.headers[name] for name in PASS_BACK if name in res.headers})
