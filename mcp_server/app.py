"""The ASGI app: the MCP endpoint at /mcp, behind a gate that refuses any request without a well-formed AWDAX API key."""

from __future__ import annotations

import json
from typing import Any

from mcp_server.server import key_from_headers, mcp


class ApiKeyGate:
    """Answers 401 (with the standard Bearer challenge) before MCP sees a request that carries no AWDAX key.

    Only the shape is checked here; the API checks that the key is real, belongs to someone, and is not revoked, on every
    tool call, so a revoked key stops working at once."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            if not key_from_headers(headers):
                body = json.dumps({"detail": "Send your AWDAX API key as `Authorization: Bearer awx_...`."}).encode()
                await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def build_app() -> Any:
    # Stateless + JSON replies: each call stands alone, so it passes through the site's proxy and a tunnel unchanged.
    return ApiKeyGate(mcp.streamable_http_app(json_response=True, stateless_http=True))
