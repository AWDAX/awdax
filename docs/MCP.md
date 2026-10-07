# AWDAX as an MCP server (connect Claude)

Claude can start research, check progress, read the collected table and ask questions about it, **as your account**.
It uses an API key; it never sees anyone else's chats.

## 1. Run it

The MCP server is a small separate process that sits beside the API and calls it with the caller's own key.

```bash
python app.py           # the API, port 8000
python -m mcp_server    # the MCP server, 127.0.0.1:8001 (MCP_PORT to change)
```

With Docker (docs/DEPLOY.md) the `mcp` container runs it for you, beside the API.

The API forwards `https://<site>/api/mcp` to it, so Claude connects at the site's own address, through the same
reverse proxy as the app. Nothing else needs exposing.

| Variable | Default | What |
|---|---|---|
| `MCP_PORT` | `8001` | Where the MCP server listens (loopback only). |
| `MCP_UPSTREAM` | `http://127.0.0.1:$MCP_PORT` | Where the API's `/api/mcp` route sends requests. |
| `AWDAX_INTERNAL_API` | `http://127.0.0.1:8000` | Where the MCP server reaches the API. |

## 2. Make a key

Sign in, open **API & MCP** in the sidebar, and create a key. Choose **Read and write** if Claude should start
research runs; **Read only** can list, read and ask, but not start anything. The key is shown once.

## 3. Connect

**Claude Code**

```bash
claude mcp add --transport http awdax https://<site>/api/mcp --header "Authorization: Bearer awx_YOUR_KEY"
```

**Claude Desktop** (`claude_desktop_config.json`, through the `mcp-remote` bridge):

```json
{
  "mcpServers": {
    "awdax": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://<site>/api/mcp", "--header", "Authorization: Bearer awx_YOUR_KEY"]
    }
  }
}
```

**claude.ai (Connectors)**: custom connectors accept a fixed header only where an organisation owner can add request
headers (a beta that is not on for every organisation). Everyone else needs OAuth, which AWDAX does not offer yet (see
"Later" below). Use Claude Code or Claude Desktop meanwhile.

## What Claude can do

| Tool | Does |
|---|---|
| `list_chats` | This account's research chats. |
| `start_research` | Starts a run from a plain request (web data, local businesses on Google Maps, eGazette). Local-business runs also read each business's own website for its email, social links and site problems. For "near me" Claude passes `near_lat` and `near_lng`. Needs a read and write key. |
| `get_run_status` | `running`, `succeeded` or `failed`, the phase, rows so far, and the run's summary when finished. |
| `get_dataset` | The table, a page at a time (up to 200 rows), each row an object keyed by column. |
| `get_sources` | The pages or Maps searches the run used. |
| `ask_data` | Exact calculations over the table: totals, averages, medians, top N, groupings, shares, growth, ratios. |

Try: *"Using AWDAX, find cafes in Bandra with phone numbers, then tell me the average rating and the five most reviewed."*

## How it is kept safe

- Every tool call goes to the API with the caller's key. Which chats the key sees, whether it may write, and its rate
  limit (120 requests a minute per key) are decided there, once.
- A request with no well-formed key is refused with `401` before MCP sees it. A revoked key stops working on its
  next call.
- A key cannot create or revoke keys, so a leaked key cannot mint others. Revoke it on the same page.
- The MCP server listens on loopback only and does not open the database.

## Check it

```bash
npx @modelcontextprotocol/inspector   # URL: http://127.0.0.1:8001/mcp, header Authorization: Bearer awx_...
```

## Later

OAuth sign-in (so any claude.ai user can press **Connect**) needs discovery metadata, dynamic client registration and
PKCE, with the callback `https://claude.ai/api/mcp/auth_callback`. It is a separate piece of work.
