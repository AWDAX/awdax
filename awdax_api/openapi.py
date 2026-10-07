"""
The API's OpenAPI 3.1 description, served at GET /api/openapi.json and shown on the app's Developers page.

Written by hand so it can say what each call is for. tests/test_awdax_api/test_openapi.py compares it with the routes
Flask actually has, so a new route without a description (or a description of a removed route) fails the build.
"""

from __future__ import annotations

from typing import Any

from flask import jsonify

from awdax_api.routes import bp

INSTANCE_ID = {"name": "instance_id", "in": "path", "required": True, "description": "The chat's id, from POST /api/instances.", "schema": {"type": "string"}}
KEY_ID = {"name": "key_id", "in": "path", "required": True, "schema": {"type": "string"}}
INCLUDE_PARTIAL = {"name": "include_partial", "in": "query", "schema": {"type": "boolean", "default": False}}


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json(schema: dict[str, Any]) -> dict[str, Any]:
    return {"application/json": {"schema": schema}}


def _op(summary: str, tag: str, *, description: str = "", params: list | None = None, body: dict | None = None,
        ok: tuple[str, str, dict | None] = ("200", "OK", None), errors: tuple[str, ...] = ("401", "404"), public: bool = False) -> dict[str, Any]:
    status, text, schema = ok
    out: dict[str, Any] = {"summary": summary, "tags": [tag], "responses": {}}
    if description:
        out["description"] = description
    if params:
        out["parameters"] = params
    if body is not None:
        out["requestBody"] = {"required": True, "content": _json(body)}
    out["responses"][status] = {"description": text, **({"content": _json(schema)} if schema else {})}
    for code in errors:
        out["responses"][code] = {"description": {"400": "Invalid request", "401": "Missing or invalid credentials", "403": "Not allowed for this key",
                                                  "404": "Not found, or not yours", "409": "Conflict", "429": "Too many requests", "503": "Unavailable"}[code],
                                  "content": _json(_ref("Error"))}
    if public:
        out["security"] = []
    return out


READ = ("401", "404", "429")
SCHEMAS: dict[str, Any] = {
    "Error": {"type": "object", "properties": {"detail": {"type": "string"}}, "required": ["detail"]},
    "Instance": {
        "type": "object",
        "properties": {
            "id": {"type": "string"}, "title": {"type": "string"}, "goal": {"type": "string"}, "archived": {"type": "boolean"},
            "live_enabled": {"type": "boolean"}, "created_at": {"type": "string"}, "updated_at": {"type": "string"},
            "dataset_row_count": {"type": "integer", "description": "Only on single-chat reads."},
        },
    },
    "Message": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "instance_id": {"type": "string"}, "role": {"enum": ["user", "assistant"]}, "content": {"type": "string"}, "created_at": {"type": "string"}},
    },
    "LiveState": {
        "type": "object",
        "properties": {
            "enabled": {"type": "boolean"}, "rows_total": {"type": "integer"}, "interval_seconds": {"type": "integer"},
            "latest_run": {"type": ["object", "null"], "description": "status (running|succeeded|failed), phase, detail, rows_total, updated_at"},
        },
    },
    "Dataset": {
        "type": "object",
        "properties": {
            "columns": {"type": "array", "items": {"type": "string"}},
            "column_labels": {"type": "array", "items": {"type": "string"}, "description": "Readable headers, aligned with columns."},
            "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
            "row_count": {"type": "integer"},
            "records": {"type": "array", "items": {"type": "object"}, "description": "One per row: id, source_url, source_domain."},
        },
    },
    "AskColumn": {
        "type": "object", "required": ["index", "key"],
        "properties": {"index": {"type": "integer"}, "key": {"type": "string"}, "label": {"type": "string"},
                       "kind": {"enum": ["number", "money", "percent", "period", "category", "url", "text", "empty"]}, "unit": {"type": "string"}},
    },
    "AskRequest": {
        "type": "object", "required": ["question", "columns", "rows"],
        "properties": {"question": {"type": "string", "maxLength": 500}, "columns": {"type": "array", "items": _ref("AskColumn")},
                       "rows": {"type": "array", "items": {"type": "object"}, "maxItems": 5000}},
    },
    "AskAnswer": {
        "type": "object",
        "description": "From /api/ask: kind query (a plan the browser runs), computed or refuse. From /api/instances/{id}/ask: kind answer (calculated here) or refuse.",
        "properties": {"kind": {"enum": ["query", "computed", "answer", "refuse"]}, "source": {"enum": ["fast", "plan", "calculation"]}, "reason": {"type": "string"},
                       "meaning": {"type": "string", "description": "What was calculated, in a sentence."},
                       "columns": {"type": "array", "items": {"type": "object"}}, "rows": {"type": "array", "items": {"type": "array", "items": {}}},
                       "overall": {"type": ["number", "null"], "description": "The same figure over all rows used (the grand total, overall average, ...)."},
                       "matched": {"type": "integer"}, "used": {"type": "integer"},
                       "excluded_count": {"type": "integer", "description": "Cells that were not numbers and were left out."}},
    },
    "ApiKey": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "prefix": {"type": "string"}, "scopes": {"type": "array", "items": {"enum": ["read", "write"]}},
                       "created_at": {"type": "string"}, "last_used_at": {"type": ["string", "null"]}},
    },
    "CreatedApiKey": {"allOf": [_ref("ApiKey"), {"type": "object", "properties": {"key": {"type": "string", "description": "The key itself. Shown once, never again."}}}]},
}


def build_spec() -> dict[str, Any]:
    ask_body_note = "Answers a question about a table you send. Costs one model call; limited to 20 questions per 5 minutes per account."
    paths: dict[str, dict[str, Any]] = {
        "/health": {"get": _op("Liveness check", "System", ok=("200", "The server is up", None), errors=(), public=True)},
        "/ready": {"get": _op("Readiness check", "System", ok=("200", "The server is ready", None), errors=(), public=True)},
        "/api/openapi.json": {"get": _op("This document", "System", errors=(), public=True)},
        "/api/me": {"get": _op("Who the credentials belong to", "System", description="Use it to check an API key works.", errors=("401",))},
        "/api/keys": {
            "get": _op("List this account's active API keys", "API keys", description="Signed-in sessions only.", ok=("200", "Keys, newest first", {"type": "array", "items": _ref("ApiKey")}), errors=("401", "403")),
            "post": _op("Create an API key", "API keys", description="Signed-in sessions only. The key is in the response once.",
                        body={"type": "object", "properties": {"name": {"type": "string"}, "scopes": {"type": "array", "items": {"enum": ["read", "write"]}, "default": ["read"]}}},
                        ok=("201", "Created", _ref("CreatedApiKey")), errors=("400", "401", "403", "409")),
        },
        "/api/keys/{key_id}": {"delete": _op("Revoke an API key", "API keys", params=[KEY_ID], ok=("204", "Revoked", None), errors=("401", "403", "404"))},
        "/api/instances": {
            "get": _op("List your chats", "Chats", ok=("200", "Chats, newest first", {"type": "array", "items": _ref("Instance")}), errors=("401", "429")),
            "post": _op("Create an empty chat", "Chats", body={"type": "object", "properties": {"title": {"type": "string", "maxLength": 80}, "goal": {"type": "string", "maxLength": 2000}}},
                        ok=("201", "Created", _ref("Instance")), errors=("400", "401", "403", "429")),
        },
        "/api/instances/{instance_id}": {
            "get": _op("One chat", "Chats", params=[INSTANCE_ID], ok=("200", "The chat", _ref("Instance")), errors=READ),
            "patch": _op("Rename, archive, or switch live tracking", "Chats", params=[INSTANCE_ID],
                         body={"type": "object", "properties": {"title": {"type": "string"}, "archived": {"type": "boolean"}, "live_enabled": {"type": "boolean"}}},
                         ok=("200", "The updated chat", _ref("Instance")), errors=("401", "403", "404", "429")),
            "delete": _op("Delete a chat and its data", "Chats", params=[INSTANCE_ID], ok=("204", "Deleted", None), errors=("401", "403", "404", "429")),
        },
        "/api/instances/{instance_id}/messages": {
            "get": _op("The chat's messages", "Research", params=[INSTANCE_ID], ok=("200", "Messages, oldest first", {"type": "array", "items": _ref("Message")}), errors=READ),
            "post": _op(
                "Start a research run", "Research", params=[INSTANCE_ID],
                description=("Describes what to find: web data, local businesses on Google Maps (\"cafes in Pune\", \"leads in Delhi NCR\"), or eGazette notifications. "
                             "Runs in the background; poll /live or the dataset. 409 while a run is active; 429 when too many runs are active."),
                body={"type": "object", "required": ["content"],
                      "properties": {"content": {"type": "string", "maxLength": 2000}, "max_pages": {"type": "integer", "minimum": 1, "maximum": 10},
                                     "location": {"type": "object", "description": "Where the user is, for \"near me\" searches.",
                                                  "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}}}}},
                ok=("201", "The chat's messages, including the one just sent", {"type": "array", "items": _ref("Message")}), errors=("400", "401", "403", "404", "409", "429")),
        },
        "/api/instances/{instance_id}/dataset": {
            "get": _op("The collected table", "Data", params=[INSTANCE_ID, {"name": "limit", "in": "query", "schema": {"type": "integer", "maximum": 5000, "default": 5000}}, INCLUDE_PARTIAL],
                       ok=("200", "Columns and rows", _ref("Dataset")), errors=READ),
            "delete": _op("Remove the collected rows (the chat stays)", "Data", params=[INSTANCE_ID], ok=("204", "Cleared", None), errors=("401", "403", "404", "409", "429")),
        },
        "/api/instances/{instance_id}/dashboard": {"get": _op("Chat summary plus its table", "Data", params=[INSTANCE_ID], errors=READ)},
        "/api/instances/{instance_id}/live": {
            "get": _op("Run status and live-tracking state", "Research", params=[INSTANCE_ID], ok=("200", "Current state", _ref("LiveState")), errors=READ),
            "patch": _op("Turn live tracking on or off", "Research", params=[INSTANCE_ID], body={"type": "object", "properties": {"enabled": {"type": "boolean"}}},
                         ok=("200", "Current state", _ref("LiveState")), errors=("401", "403", "404", "429")),
        },
        "/api/instances/{instance_id}/live/stream": {
            "get": {**_op("Live events (Server-Sent Events)", "Research", params=[INSTANCE_ID], description="Events: status, run_event, source. A keepalive comment every 15 s. Prefer polling /live from scripts.", errors=READ),
                    "responses": {"200": {"description": "text/event-stream", "content": {"text/event-stream": {"schema": {"type": "string"}}}}, "401": {"description": "Missing or invalid credentials"}, "404": {"description": "Not found, or not yours"}}},
        },
        "/api/instances/{instance_id}/sources": {"get": _op("Sources the run used", "Data", params=[INSTANCE_ID], errors=READ)},
        "/api/instances/{instance_id}/failed-links": {
            "get": _op("Links the run could not read with a plain web request, and the research ranking", "Data", params=[INSTANCE_ID], errors=READ)
        },
        "/api/instances/{instance_id}/dataset/stats": {"get": _op("Row counts by quality tier", "Data", params=[INSTANCE_ID], errors=READ)},
        "/api/instances/{instance_id}/dataset/rescore": {"post": _op("Re-apply scoring after a run", "Data", params=[INSTANCE_ID], errors=("401", "403", "404", "409", "429"))},
        "/api/instances/{instance_id}/graph/parameters": {"get": _op("Numeric columns a chart can use", "Data", params=[INSTANCE_ID, INCLUDE_PARTIAL], errors=READ)},
        "/api/instances/{instance_id}/graph": {"get": _op("Chart data", "Data", params=[INSTANCE_ID, INCLUDE_PARTIAL, {"name": "parameters", "in": "query", "description": "Comma-separated column keys.", "schema": {"type": "string"}}], errors=READ)},
        "/api/mcp": {
            m: _op(
                f"MCP endpoint ({m.upper()})", "MCP",
                description=("Model Context Protocol over streamable HTTP (stateless, JSON replies). Point Claude here with a read and write API key. "
                             "Tools: list_chats, start_research, get_run_status, get_dataset, get_sources, ask_data."),
                ok=("200", "A JSON-RPC reply", None), errors=("401", "429", "503"),
            )
            for m in ("get", "post", "delete")
        },
        "/api/instances/{instance_id}/ask": {
            "post": _op(
                "Ask a question about this chat's table", "Ask", params=[INSTANCE_ID],
                description=("The server reads this chat's table, works out the answer exactly and says what it calculated. Plain questions "
                             "(counts, totals, averages, top N, by category) are answered at once; others use one model call, limited to 20 per 5 minutes per account."),
                body={"type": "object", "required": ["question"], "properties": {"question": {"type": "string", "maxLength": 500, "examples": ["average rating by category", "top 5 by reviews", "what share of places have no website?"]}}},
                ok=("200", "An answer table, or a refusal that says why", _ref("AskAnswer")), errors=("400", "401", "404", "429", "503"),
            )
        },
        "/api/ask": {"post": _op("Ask a question about a table you send", "Ask", description=ask_body_note, body=_ref("AskRequest"), ok=("200", "A query plan, a computed table, or a refusal", _ref("AskAnswer")), errors=("400", "401", "403", "429", "503"))},
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "AWDAX API",
            "version": "1.0.0",
            "description": ("Everything the app does, as an API, per account. Create an API key on the Developers page and send it as "
                            "`Authorization: Bearer awx_...`. A key sees only its own account's chats. Read-only keys can only GET."),
        },
        "servers": [{"url": "/"}],
        "security": [{"apiKey": []}],
        "tags": [{"name": n} for n in ("System", "API keys", "Chats", "Research", "Data", "Ask", "MCP")],
        "paths": paths,
        "components": {
            "securitySchemes": {"apiKey": {"type": "http", "scheme": "bearer", "bearerFormat": "awx_...", "description": "An AWDAX API key. `X-API-Key: awx_...` also works."}},
            "schemas": SCHEMAS,
        },
    }


@bp.get("/api/openapi.json")
def openapi_json():
    return jsonify(build_spec())
