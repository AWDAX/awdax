# Running AWDAX on your machine

## One-time setup

```bash
python -m venv .venv                       # Python 3.12 or newer
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
cp .env.example .env                       # then set GEMINI_API_KEY, SUPABASE_URL and API_KEY_PEPPER (docs/CONFIGURATION.md)
cd Frontend && npm ci                      # Node 24
```

Chrome must be installed (pages that need a browser use it; Selenium finds the driver itself).

## Run it

```bash
.venv/Scripts/python app.py                # backend, http://127.0.0.1:8000 (PORT in .env changes it)
cd Frontend && npm run dev                 # website, http://localhost:5173/app  (proxies /api to the backend)
```

Optional, for Claude: `.venv/Scripts/python -m mcp_server` in a third terminal (docs/MCP.md).

If the backend runs on another port, put `AWDAX_API=http://127.0.0.1:<port>` in `Frontend/.env.local` and restart `npm run dev`.

## Signing in

The backend is strict by default: a request must carry a sign-in it can verify, or it gets 401.

- **With Google sign-in** (`npm run dev`): put the Supabase project's public values in `Frontend/.env.local`
  (`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`), set `SUPABASE_URL` in `.env`, and add `http://localhost:5173` to the project's redirect URLs.
- **Without signing in** (`npm run dev:agent`, http://localhost:5174/app): add `AWDAX_AUTH_MODE=dev` to `.env`. Local use only; never on a server.

## Tests

```bash
.venv/Scripts/python -m unittest discover -s tests/test_awdax_api -t tests/test_awdax_api
.venv/Scripts/python -m unittest discover -s tests -t tests -p "test_*.py"
cd Frontend && npm run lint && npm test && npm run build
```

No test needs the network, a browser or an API key.

## Common problems

| Problem | Cause and fix |
|---|---|
| 401 on everything | The backend is strict and you are not signed in: sign in, or use `AWDAX_AUTH_MODE=dev` with `npm run dev:agent`. |
| "Can't reach the AWDAX server" | The backend is not running, or `AWDAX_API` in `Frontend/.env.local` names another port. |
| The page sits on "loading" and the backend window prints nothing | On Windows, selecting text in the backend's console pauses the program. Press Esc in that window, or turn off QuickEdit Mode, or run it in the editor's terminal. |
| Port 8000 does not answer although the backend says it is running | Another (dead) process still holds the port. Use a different `PORT`, or restart the machine. |
| A chat says "Waiting for a free slot" | The run limits (`AWDAX_MAX_RUNS_PER_USER`) are reached by your other chats; they start by themselves, or pause one. |
| Maps requests give web results | `GOOGLE_MAPS_API_KEY` missing, or Places API (New) not enabled for the key. |

Deploying to a server: docs/DEPLOY.md.
