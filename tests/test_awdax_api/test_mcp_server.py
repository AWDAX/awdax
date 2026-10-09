"""Phase 4: the MCP server. A real MCP server runs on a local port; its upstream is either a mock of the API (unit tests)
or the real Flask app (end-to-end), reached through the real /api/mcp gateway."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import jwt  # noqa: E402
import uvicorn  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import ui_sessions  # noqa: E402
from mcp_server import server as mcp_module  # noqa: E402
from mcp_server.app import build_app  # noqa: E402

SECRET = "mcp-test-secret-mcp-test-secret-1234567890-abcdef"
KEY = "awx_" + "k" * 43
JSON_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

_mcp: uvicorn.Server | None = None
_mcp_port = 0


def setUpModule():
    """One MCP server for the module: the SDK's session manager can only be started once per process."""
    global _mcp, _mcp_port
    _mcp = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=0, log_level="error"))
    threading.Thread(target=_mcp.run, daemon=True).start()
    deadline = time.time() + 15
    while not _mcp.started and time.time() < deadline:
        time.sleep(0.02)
    _mcp_port = _mcp.servers[0].sockets[0].getsockname()[1]


def tearDownModule():
    if _mcp:
        _mcp.should_exit = True


_http = httpx.Client(timeout=30)  # one client: building one per request costs more than the request


def rpc(url, method, params=None, headers=None):
    res = _http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}, headers={**JSON_HEADERS, **(headers or {})}, timeout=30)
    return res


def call_tool(url, name, arguments=None, key=KEY, headers=None):
    """(is_error, text, structured) of one tool call."""
    res = rpc(url, "tools/call", {"name": name, "arguments": arguments or {}}, headers=headers if headers is not None else {"Authorization": f"Bearer {key}"})
    assert res.status_code == 200, (res.status_code, res.text)
    result = res.json()["result"]
    content = result["content"]
    return result["isError"], (content[0]["text"] if content else ""), result.get("structuredContent")


class ToolTests(unittest.TestCase):
    """The tools against a mock of the AWDAX API."""

    def setUp(self):
        self.url = f"http://127.0.0.1:{_mcp_port}/mcp"
        self.calls: list[tuple[str, str, str | None, object]] = []
        self.routes: dict[tuple[str, str], object] = {}
        mcp_module._transport = httpx.MockTransport(self._api)
        self.addCleanup(setattr, mcp_module, "_transport", None)

    def _api(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, request.headers.get("authorization"), body))
        answer = self.routes.get((request.method, request.url.path))
        if callable(answer):
            return answer(request)
        if answer is None:
            return httpx.Response(404, json={"detail": "Instance not found"})
        return httpx.Response(200, json=answer)

    def test_a_request_without_a_well_formed_key_is_refused_before_mcp(self):
        for headers in ({}, {"Authorization": "Bearer sk-123"}, {"Authorization": "Basic abc"}, {"X-API-Key": "nope"}):
            res = rpc(self.url, "tools/list", headers=headers)
            self.assertEqual(res.status_code, 401, headers)
            self.assertEqual(res.headers["www-authenticate"], "Bearer")
        self.assertEqual(self.calls, [])

    def test_the_tools_are_listed_with_descriptions(self):
        tools = rpc(self.url, "tools/list", headers={"Authorization": f"Bearer {KEY}"}).json()["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"list_chats", "start_research", "get_run_status", "get_dataset", "get_sources", "ask_data"})
        for t in tools:
            self.assertGreater(len(t["description"]), 40, t["name"])
        schema = next(t for t in tools if t["name"] == "start_research")["inputSchema"]
        self.assertEqual(schema["required"], ["request"])

    def test_the_callers_own_key_is_what_the_api_sees(self):
        self.routes[("GET", "/api/instances")] = [{"id": "c1", "title": "Cafes", "goal": "cafes in pune", "updated_at": "t", "live_enabled": False}]
        err, _, data = call_tool(self.url, "list_chats")
        self.assertFalse(err)
        self.assertEqual(data["result"], [{"chat_id": "c1", "title": "Cafes", "request": "cafes in pune", "updated_at": "t", "live_tracking": False}])
        other = "awx_" + "z" * 43
        call_tool(self.url, "list_chats", key=other)
        call_tool(self.url, "list_chats", headers={"X-API-Key": "awx_" + "y" * 43})
        self.assertEqual([c[2] for c in self.calls], [f"Bearer {KEY}", f"Bearer {other}", "Bearer awx_" + "y" * 43])

    def test_start_research_creates_a_chat_then_sends_the_request(self):
        self.routes[("POST", "/api/instances")] = {"id": "c9"}
        self.routes[("POST", "/api/instances/c9/messages")] = []
        err, _, data = call_tool(self.url, "start_research", {"request": "cafes near me", "near_lat": 18.52, "near_lng": 73.85})
        self.assertFalse(err)
        self.assertEqual((data["chat_id"], data["status"]), ("c9", "started"))
        self.assertEqual(self.calls[0][1:2] + (self.calls[0][3],), ("/api/instances", {"title": "cafes near me"}))
        self.assertEqual(self.calls[1][3], {"content": "cafes near me", "location": {"lat": 18.52, "lng": 73.85}})
        self.assertEqual(len(self.calls), 2)

    def test_start_research_cleans_up_when_the_run_is_refused(self):
        self.routes[("POST", "/api/instances")] = {"id": "c9"}
        self.routes[("POST", "/api/instances/c9/messages")] = lambda r: httpx.Response(429, json={"detail": "Too many runs are active right now."})
        self.routes[("DELETE", "/api/instances/c9")] = lambda r: httpx.Response(204)
        err, text, _ = call_tool(self.url, "start_research", {"request": "cafes in pune"})
        self.assertTrue(err)
        self.assertIn("Too many runs are active", text)
        self.assertIn(("DELETE", "/api/instances/c9"), [c[:2] for c in self.calls])

    def test_start_research_checks_its_own_arguments_before_calling_the_api(self):
        for args in ({"request": "  "}, {"request": "x", "near_lat": 1.0}):
            err, _, _ = call_tool(self.url, "start_research", args)
            self.assertTrue(err, args)
        self.assertEqual(self.calls, [])

    def test_run_status_includes_the_summary_only_when_finished(self):
        self.routes[("GET", "/api/instances/c1/live")] = {"rows_total": 7, "latest_run": {"status": "running", "phase": "extracting", "detail": "Searching", "updated_at": "t"}}
        err, _, data = call_tool(self.url, "get_run_status", {"chat_id": "c1"})
        self.assertEqual((data["status"], data["phase"], data["rows"]), ("running", "extracting", 7))
        self.assertNotIn("summary", data)
        self.routes[("GET", "/api/instances/c1/live")] = {"rows_total": 7, "latest_run": {"status": "succeeded", "phase": "complete"}}
        self.routes[("GET", "/api/instances/c1/messages")] = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "Run complete. " + "x" * 3000}]
        _, _, data = call_tool(self.url, "get_run_status", {"chat_id": "c1"})
        self.assertEqual(data["status"], "succeeded")
        self.assertTrue(data["summary"].startswith("Run complete."))
        self.assertLessEqual(len(data["summary"]), 1500)

    def test_a_chat_that_has_not_run_is_not_started(self):
        self.routes[("GET", "/api/instances/c1/live")] = {"rows_total": 0, "latest_run": None}
        _, _, data = call_tool(self.url, "get_run_status", {"chat_id": "c1"})
        self.assertEqual(data["status"], "not_started")

    def test_the_dataset_is_paged_and_keyed_by_column(self):
        self.routes[("GET", "/api/instances/c1/dataset")] = {"columns": ["name", "phone"], "rows": [[f"n{i}", f"p{i}"] for i in range(10)]}
        _, _, data = call_tool(self.url, "get_dataset", {"chat_id": "c1", "limit": 3, "offset": 4})
        self.assertEqual((data["total"], data["offset"], data["returned"]), (10, 4, 3))
        self.assertEqual(data["rows"][0], {"name": "n4", "phone": "p4"})
        _, _, data = call_tool(self.url, "get_dataset", {"chat_id": "c1", "limit": 99999, "offset": -5})
        self.assertEqual((data["offset"], data["returned"]), (0, 10))
        _, _, data = call_tool(self.url, "get_dataset", {"chat_id": "c1", "offset": 50})
        self.assertEqual((data["returned"], data["rows"]), (0, []))

    def test_the_row_limit_is_capped(self):
        self.routes[("GET", "/api/instances/c1/dataset")] = {"columns": ["a"], "rows": [[str(i)] for i in range(500)]}
        _, _, data = call_tool(self.url, "get_dataset", {"chat_id": "c1", "limit": 1000})
        self.assertEqual(data["returned"], 200)

    def test_sources_are_trimmed_to_what_is_useful(self):
        self.routes[("GET", "/api/instances/c1/sources")] = {
            "candidate_count": 1, "sources": [{"id": "1", "url": "https://a.test", "title": "A", "status": "complete", "accepted": 4, "rank_reasons": [], "deep_notes": [], "reason": ""}],
        }
        _, _, data = call_tool(self.url, "get_sources", {"chat_id": "c1"})
        self.assertEqual(data["sources"], [{"url": "https://a.test", "title": "A", "status": "complete", "accepted": 4}])

    def test_ask_data_sends_the_question_and_returns_the_answer(self):
        self.routes[("POST", "/api/instances/c1/ask")] = {"kind": "answer", "columns": [{"name": "Average rating"}], "rows": [[4.2]]}
        _, _, data = call_tool(self.url, "ask_data", {"chat_id": "c1", "question": "average rating"})
        self.assertEqual(data["rows"], [[4.2]])
        self.assertEqual(self.calls[-1][3], {"question": "average rating"})

    def test_api_errors_become_readable_tool_errors(self):
        for status, detail, expected in (
            (404, "Instance not found", "Instance not found (HTTP 404)"),
            (403, "This API key is read-only.", "read-only"),
            (401, "Your sign-in could not be verified.", "not valid, or it was revoked"),
            (429, "Too many requests for this API key", "Too many requests"),
        ):
            self.routes[("GET", "/api/instances")] = lambda r, s=status, d=detail: httpx.Response(s, json={"detail": d})
            err, text, _ = call_tool(self.url, "list_chats")
            self.assertTrue(err, status)
            self.assertIn(expected, text)

    def test_an_unreachable_api_is_a_plain_message(self):
        def down(request):
            raise httpx.ConnectError("refused")

        self.routes[("GET", "/api/instances")] = down
        err, text, _ = call_tool(self.url, "list_chats")
        self.assertTrue(err)
        self.assertIn("did not answer", text)


class EndToEndTests(unittest.TestCase):
    """Real Flask API + the /api/mcp gateway + the MCP server, with real keys: what Claude actually goes through."""

    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._patches = [
            mock.patch.object(ui_sessions, "DB_PATH", Path(cls._dir.name) / "t.sqlite"),
            # Not clear=True: the MCP server's threads still need PATH and friends. Strict mode is spelled out.
            mock.patch.dict(os.environ, {"SUPABASE_JWT_SECRET": SECRET, "AWDAX_AUTH_MODE": "strict", "PROXY_SHARED_SECRET": ""}),
        ]
        for p in cls._patches:
            p.start()
        ui_sessions._initialized = None
        import app as app_module

        cls.flask = make_server("127.0.0.1", 0, app_module.app, threaded=True)
        threading.Thread(target=cls.flask.serve_forever, daemon=True).start()
        cls.site = f"http://127.0.0.1:{cls.flask.server_port}"
        os.environ["AWDAX_INTERNAL_API"] = cls.site
        os.environ["MCP_UPSTREAM"] = f"http://127.0.0.1:{_mcp_port}"
        cls.gateway = f"{cls.site}/api/mcp"

    @classmethod
    def tearDownClass(cls):
        cls.flask.shutdown()
        for p in reversed(cls._patches):
            p.stop()
        ui_sessions._initialized = None
        cls._dir.cleanup()

    def _key(self, sub, scopes=("read", "write")):
        session = {"Authorization": "Bearer " + jwt.encode({"sub": sub, "app_metadata": {"provider": "google"}}, SECRET, algorithm="HS256")}
        res = _http.post(f"{self.site}/api/keys", json={"name": "t", "scopes": list(scopes)}, headers=session)
        self.assertEqual(res.status_code, 201, res.text)
        return res.json()

    def test_claude_can_run_research_and_read_it_back_as_one_account(self):
        key = self._key("alice")["key"]
        with mock.patch("awdax_api.routes.submit_run") as start:
            err, _, started = call_tool(self.gateway, "start_research", {"request": "cafes in Pune"}, key=key)
        self.assertFalse(err)
        start.assert_called_once()
        self.assertEqual(start.call_args.args[1], "cafes in Pune")
        chat_id = started["chat_id"]
        _, _, chats = call_tool(self.gateway, "list_chats", key=key)
        self.assertEqual([c["chat_id"] for c in chats["result"]], [chat_id])
        err, _, status = call_tool(self.gateway, "get_run_status", {"chat_id": chat_id}, key=key)
        self.assertEqual((err, status["status"], status["rows"]), (False, "not_started", 0))
        err, _, data = call_tool(self.gateway, "get_dataset", {"chat_id": chat_id}, key=key)
        self.assertEqual((err, data["total"], data["rows"]), (False, 0, []))

    def test_claude_gets_exact_figures_from_ask_data(self):
        key = self._key("grace")["key"]
        with mock.patch("awdax_api.routes.submit_run"):
            _, _, started = call_tool(self.gateway, "start_research", {"request": "cafes in Pune"}, key=key)
        table = {
            "columns": ["name", "price", "rating"], "column_labels": ["Name", "Price", "Rating"], "row_count": 4, "records": [],
            "rows": [["A", "₹12.5 Lakh", "4.5"], ["B", "₹8,50,000", "4.0"], ["C", "N/A", "3.5"], ["D", "₹1.2 Crore", "N/A"]],
        }
        with mock.patch("awdax_api.ask_routes.build_dataset_table", return_value=table), mock.patch("ask_data.llm_json", side_effect=AssertionError("not needed")):
            err, _, total = call_tool(self.gateway, "ask_data", {"chat_id": started["chat_id"], "question": "total price"}, key=key)
            _, _, average = call_tool(self.gateway, "ask_data", {"chat_id": started["chat_id"], "question": "average rating"}, key=key)
        self.assertFalse(err)
        self.assertEqual(total["rows"][0][1], 1250000 + 850000 + 12000000)  # the missing price is left out, not counted as 0
        self.assertEqual(total["used"], 3)
        self.assertEqual(average["rows"][0][1], 4)  # (4.5 + 4.0 + 3.5) / 3, the one N/A left out
        self.assertEqual(average["used"], 3)
        self.assertIn("average rating", average["meaning"].lower())

    def test_one_accounts_key_never_reaches_another_accounts_chats(self):
        alice, bob = self._key("alice")["key"], self._key("bob")["key"]
        with mock.patch("awdax_api.routes.submit_run"):
            _, _, started = call_tool(self.gateway, "start_research", {"request": "private to alice"}, key=alice)
        chat_id = started["chat_id"]
        _, _, bobs = call_tool(self.gateway, "list_chats", key=bob)
        self.assertEqual(bobs["result"], [])
        for tool in ("get_run_status", "get_dataset", "get_sources"):
            err, text, _ = call_tool(self.gateway, tool, {"chat_id": chat_id}, key=bob)
            self.assertTrue(err, tool)
            self.assertIn("not found", text.lower())

    def test_a_read_only_key_can_read_but_cannot_start_a_run(self):
        key = self._key("carol", scopes=("read",))["key"]
        err, text, _ = call_tool(self.gateway, "list_chats", key=key)
        self.assertFalse(err)
        err, text, _ = call_tool(self.gateway, "start_research", {"request": "anything"}, key=key)
        self.assertTrue(err)
        self.assertIn("read-only", text)
        _, _, chats = call_tool(self.gateway, "list_chats", key=key)
        self.assertEqual(chats["result"], [], "the refused request left no empty chat behind")

    def test_a_revoked_key_stops_working_at_once(self):
        made = self._key("dave")
        self.assertFalse(call_tool(self.gateway, "list_chats", key=made["key"])[0])
        session = {"Authorization": "Bearer " + jwt.encode({"sub": "dave", "app_metadata": {"provider": "google"}}, SECRET, algorithm="HS256")}
        self.assertEqual(_http.delete(f"{self.site}/api/keys/{made['id']}", headers=session).status_code, 204)
        # refused by the API's own check at the gateway: the key no longer resolves
        self.assertEqual(rpc(self.gateway, "tools/list", headers={"Authorization": f"Bearer {made['key']}"}).status_code, 401)

    def test_the_gateway_refuses_a_caller_with_no_credentials_and_a_session_without_a_key(self):
        self.assertEqual(rpc(self.gateway, "tools/list").status_code, 401)
        session = {"Authorization": "Bearer " + jwt.encode({"sub": "erin", "app_metadata": {"provider": "google"}}, SECRET, algorithm="HS256")}
        res = rpc(self.gateway, "tools/list", headers=session)
        self.assertEqual(res.status_code, 401, "a browser session is not an MCP credential")

    def test_the_gateway_says_so_when_the_mcp_service_is_down(self):
        key = self._key("frank")["key"]
        with mock.patch.dict(os.environ, {"MCP_UPSTREAM": "http://127.0.0.1:1"}):
            res = rpc(self.gateway, "tools/list", headers={"Authorization": f"Bearer {key}"})
        self.assertEqual(res.status_code, 503)
        self.assertIn("python -m mcp_server", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()
