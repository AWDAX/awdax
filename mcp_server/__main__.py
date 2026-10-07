"""`python -m mcp_server`: serve the AWDAX MCP endpoint on 127.0.0.1:$MCP_PORT (default 8001) at /mcp.

Run it next to the API (python app.py). The API's /api/mcp route forwards to it, so the public address is the site's own."""

import os

import uvicorn

from mcp_server.app import build_app

if __name__ == "__main__":
    uvicorn.run(build_app(), host="127.0.0.1", port=int(os.getenv("MCP_PORT", "8001")), log_level="info")
