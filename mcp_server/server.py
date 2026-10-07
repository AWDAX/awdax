"""
AWDAX as an MCP server, so Claude can run research and read the results as one account.

It is a thin layer over the AWDAX HTTP API: every tool forwards the caller's own API key (`Authorization: Bearer awx_...`)
to the API and returns what it answers. Which chats a key may see, whether it may write, and its rate limit are therefore
decided in one place (the API), and this process never opens the database. Plain request/response (stateless JSON), so
it works through a tunnel and the site's proxy with no long-lived stream.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

API_KEY_PREFIX = "awx_"
MAX_ROWS = 200
TIMEOUT_S = 30

INSTRUCTIONS = (
    "AWDAX researches the web and Google Maps and keeps the results as tables. Typical use: start_research with a plain "
    "request (for example 'cafes in Pune with phone numbers'), poll get_run_status until its status is 'succeeded' "
    "(a run takes from seconds to several minutes), then get_dataset to read the rows and ask_data for totals, averages, "
    "rankings and other calculations over them. Every row has a source link; say where figures came from."
)

mcp = MCPServer("awdax", instructions=INSTRUCTIONS)

# Tests swap this for httpx.MockTransport so no network is used.
_transport: httpx.AsyncBaseTransport | None = None
_shared: tuple[tuple[str, int], httpx.AsyncClient] | None = None


def internal_api() -> str:
    return (os.getenv("AWDAX_INTERNAL_API") or "http://127.0.0.1:8000").rstrip("/")


def key_from_headers(headers: Any) -> str | None:
    """The API key a request carries: `Authorization: Bearer awx_...` or `X-API-Key: awx_...`."""
    if not headers:
        return None
    auth = (headers.get("authorization") or "").strip()
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    key = bearer if bearer.startswith(API_KEY_PREFIX) else (headers.get("x-api-key") or "").strip()
    return key if key.startswith(API_KEY_PREFIX) and len(key) <= 100 else None


def _client() -> httpx.AsyncClient:
    """One client for all calls: building one (its TLS setup) per call would cost more than the call itself."""
    global _shared
    key = (internal_api(), id(_transport))
    if _shared is None or _shared[0] != key:
        _shared = (key, httpx.AsyncClient(base_url=key[0], transport=_transport, timeout=TIMEOUT_S))
    return _shared[1]


async def _call(ctx: Context, method: str, path: str, *, body: dict[str, Any] | None = None, params: dict[str, Any] | None = None) -> Any:
    """One call to the AWDAX API as the caller. API errors become tool errors Claude can read and act on."""
    key = key_from_headers(ctx.headers)
    if not key:
        raise ToolError("No AWDAX API key was sent. Add an `Authorization: Bearer awx_...` header to this connection.")
    try:
        res = await _client().request(method, path, json=body, params=params, headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError:
        raise ToolError("The AWDAX server did not answer. Try again in a minute.") from None
    if res.status_code >= 400:
        try:
            detail = str(res.json().get("detail") or "")
        except (ValueError, AttributeError):
            detail = ""
        if res.status_code == 401:
            raise ToolError("The AWDAX API key is not valid, or it was revoked. Create a new one on the Developers page.")
        raise ToolError(f"{detail or 'The request failed'} (HTTP {res.status_code})")
    if res.status_code == 204 or not res.content:
        return None
    return res.json()


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


@mcp.tool()
async def list_chats(ctx: Context) -> list[dict[str, Any]]:
    """List this account's research chats, newest first: id, title, what was asked, when it last changed."""
    chats = await _call(ctx, "GET", "/api/instances")
    return [
        {"chat_id": c["id"], "title": c.get("title"), "request": _clip(c.get("goal") or "", 200), "updated_at": c.get("updated_at"), "live_tracking": c.get("live_enabled")}
        for c in chats
    ]


@mcp.tool()
async def start_research(ctx: Context, request: str, near_lat: float | None = None, near_lng: float | None = None) -> dict[str, Any]:
    """Start a research run from a plain-language request and return its chat_id right away.

    The request can be web data ("EV prices in India"), local businesses on Google Maps ("dental clinics in Noida",
    "restaurants in Delhi NCR that could use a website", "cafes near me"), or eGazette notifications. For "near me",
    pass near_lat and near_lng (degrees). Local-business runs also open each business's own website for its email,
    social links and site problems, so they take a few minutes. The run continues in the background: poll
    get_run_status. Needs a read and write API key; a run costs Google Maps quota when it uses Maps, so do not start
    the same request twice."""
    request = (request or "").strip()
    if not request:
        raise ToolError("Say what to research.")
    if (near_lat is None) != (near_lng is None):
        raise ToolError("Give both near_lat and near_lng, or neither.")
    chat = await _call(ctx, "POST", "/api/instances", body={"title": _clip(request, 80)})
    message: dict[str, Any] = {"content": request}
    if near_lat is not None:
        message["location"] = {"lat": near_lat, "lng": near_lng}
    try:
        await _call(ctx, "POST", f"/api/instances/{chat['id']}/messages", body=message)
    except ToolError:
        # Do not leave an empty chat behind when the run was refused (busy, bad request, read-only key).
        try:
            await _call(ctx, "DELETE", f"/api/instances/{chat['id']}")
        except ToolError:
            pass
        raise
    return {"chat_id": chat["id"], "status": "started", "next": "Call get_run_status with this chat_id until status is 'succeeded' or 'failed'."}


@mcp.tool()
async def get_run_status(ctx: Context, chat_id: str) -> dict[str, Any]:
    """Where a research run is: status (running, succeeded or failed), the current phase, rows collected so far, and,
    once it has finished, the run's own summary."""
    live = await _call(ctx, "GET", f"/api/instances/{chat_id}/live")
    run = live.get("latest_run") or {}
    out: dict[str, Any] = {
        "chat_id": chat_id,
        "status": run.get("status") or "not_started",
        "phase": run.get("phase"),
        "detail": run.get("detail"),
        "rows": live.get("rows_total", 0),
        "updated_at": run.get("updated_at"),
    }
    if out["status"] in ("succeeded", "failed"):
        messages = await _call(ctx, "GET", f"/api/instances/{chat_id}/messages")
        last = next((m for m in reversed(messages) if m.get("role") == "assistant"), None)
        if last:
            out["summary"] = _clip(last.get("content") or "", 1500)
    return out


@mcp.tool()
async def get_dataset(ctx: Context, chat_id: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """Read the table a run collected: column names and rows (each row an object keyed by column), a page at a time.
    `total` is the full row count; use offset to page. Rows carry source_url, the page each came from."""
    limit = max(1, min(int(limit), MAX_ROWS))
    offset = max(0, int(offset))
    table = await _call(ctx, "GET", f"/api/instances/{chat_id}/dataset")
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    page = rows[offset : offset + limit]
    return {
        "chat_id": chat_id,
        "columns": columns,
        "total": len(rows),
        "offset": offset,
        "returned": len(page),
        "rows": [dict(zip(columns, row)) for row in page],
    }


@mcp.tool()
async def get_sources(ctx: Context, chat_id: str) -> dict[str, Any]:
    """The sources a run used (web pages or Google Maps searches): url, title, status and how many rows came from each."""
    data = await _call(ctx, "GET", f"/api/instances/{chat_id}/sources")
    keep = ("url", "title", "status", "accepted", "reason", "domain")
    return {
        "chat_id": chat_id,
        "count": data.get("candidate_count", 0),
        "sources": [{k: s.get(k) for k in keep if s.get(k) not in (None, "")} for s in data.get("sources") or []],
    }


@mcp.tool()
async def ask_data(ctx: Context, chat_id: str, question: str) -> dict[str, Any]:
    """Ask a question about a chat's table and get the computed answer: counts, sums, averages, minimum and maximum,
    medians, top N, groupings (average rating by category), shares, growth, ratios, correlations. The answer is
    calculated exactly by the server, not estimated; the result shows what was calculated."""
    answer = await _call(ctx, "POST", f"/api/instances/{chat_id}/ask", body={"question": question})
    return answer

