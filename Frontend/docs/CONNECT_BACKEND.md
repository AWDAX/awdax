# Connect the backend to awdax.pages.dev

## Local scraper2.0 (Flask compat layer)

This repo’s React app can talk to **scraper2.0** directly: Flask serves the Awdax-shaped routes (`/api/instances`, WebSocket live) alongside the legacy `/api/sessions` API.

1. From repo root: `PORT=8000 python3 app.py` (see [`LOCAL_DEV.md`](../../LOCAL_DEV.md)).
2. From `Frontend/`: `npm run dev` (Vite proxies `/api` → `http://127.0.0.1:8000` by default).
3. New chat → `POST /api/instances/:id/messages` runs the full pipeline (including RegulatoryFeed for eGazette intents).

Production tunnel setup below still applies; point `AWDAX_API_ORIGIN` at your Flask host instead of the old FastAPI Backend repo.

---

The site calls its own `/api/*`. On Cloudflare Pages that runs `functions/api/[[path]].ts`, which checks the
visitor's Supabase sign-in and forwards the call to the AWDAX backend. The backend has no CORS or auth and is not
changed; it runs on the owner's machine and is reached through a tunnel.

```
browser ──/api/*──▶ awdax.pages.dev (Pages Function: signed in? on the list?) ──▶ tunnel ──▶ backend :8000
```

Free throughout: the Workers free plan allows 100,000 function calls a day and refuses more (no bill), and
static pages don't count. The quick tunnel needs no account.

## 1. Run the backend

`Backend/.env` needs `GEMINI_API_KEY` (free key from Google AI Studio). Delete the `GEMINI_MODEL=gemini-2.0-flash-lite`
line there, or set it to `gemini-3.5-flash-lite`: 2.0 no longer appears in Google's free-tier list.

```powershell
cd X:\Hackathons\Codecubicle\awdax\Backend
.\.venv\Scripts\python.exe app.py
```

## 2. Open a tunnel to it

Install once: `winget install --id Cloudflare.cloudflared`. Then, in a second terminal:

```powershell
cloudflared tunnel --url http://localhost:8000
```

It prints an address like `https://some-random-words.trycloudflare.com`. Keep it private: anyone with it reaches the
backend directly, without signing in. It changes every time cloudflared restarts.

## 3. Tell the site where the backend is

Cloudflare dashboard → Workers & Pages → `awdax` → Settings → Variables and Secrets → Production:

| Name | Value |
|---|---|
| `AWDAX_API_ORIGIN` | the tunnel address from step 2 (type: Secret) |
| `SUPABASE_URL` | `https://allwrzhdjodscxztcewu.supabase.co` |
| `ALLOWED_EMAILS` | optional: `a@gmail.com, b@gmail.com`. Unset lets any Google account in |

Variables apply to the next deployment. Push to `phase-1` deploys, or in GitHub → Actions → the latest
"Check and deploy frontend" run → **Re-run all jobs** redeploys the same commit.

## 4. Check it

Sign in at https://awdax.pages.dev/app and start a web request. If something is off, the app says which:

| Message | Meaning |
|---|---|
| "…isn’t connected to this site yet…" | `AWDAX_API_ORIGIN` or `SUPABASE_URL` is not set on the deployment |
| "…isn’t answering right now…" | backend or cloudflared is not running, or the tunnel address changed |
| "Your sign-in has expired…" | reload and sign in again |
| "…isn’t on the AWDAX team list…" | add the email to `ALLOWED_EMAILS`, then redeploy |

## Later: a stable address

The quick tunnel's address changes on every restart, and its stream is buffered, so the app polls every 5 s instead
(it switches by itself). A named Cloudflare Tunnel on a domain you add to Cloudflare gives a fixed address and a
real stream; only `AWDAX_API_ORIGIN` changes.
