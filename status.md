# AWDAX status

**Date:** 2 October 2026 · **Branch:** `integration/oct-02-hardening` (not yet merged to `main`, not yet deployed)
**Tests:** 155 frontend and 165 backend pass; lint clean; build passes. Real backend checked over HTTP in strict mode.
Full audit: `docs/audit/PRODUCTION_AUDIT.md` · Detailed status: `docs/SITE_STATUS.md`

---

## Two things you must do or the fix won't protect production

1. **Set `PROXY_SHARED_SECRET` to the same value on the backend and on Cloudflare Pages.** Without it, the backend stays in permissive mode and BE-01 stays open. The Pages proxy already sends the matching headers on every request path.
2. **Local development:** leave `PROXY_SHARED_SECRET` unset in your local backend `.env`. If it's set there, every local call returns 401, because the dev proxy doesn't send it. Also, scraping `localhost` now needs `AWDAX_ALLOW_PRIVATE_URLS=1`, and the old page at `http://127.0.0.1:8000/` needs `AWDAX_LEGACY_API=1`. Never set the legacy flag in production.

### How to do it

**1. Production secret**

```powershell
# Generate one value and keep it somewhere safe
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

- **Backend (production host):** add `PROXY_SHARED_SECRET=<value>` to the backend's `.env` (or its service environment) and restart the backend.
- **Cloudflare Pages:** project → Settings → Variables and Secrets → add `PROXY_SHARED_SECRET` as an encrypted variable for **Production** with the **same** value, then redeploy (a new deploy is needed for the variable to reach the function).
- **Check it worked:**
  - Calling the backend origin directly with no headers must answer **401**: `curl -i https://<backend-origin>/api/instances`.
  - The site itself must still list your chats after signing in.
  - If the site shows "Your sign-in could not be verified" everywhere, the two values differ.
- **Order:** set it on Pages and the backend within a few minutes of each other. In between, either side being ahead means 401s for everyone.

**2. Local development**

- `X:\Hackathons\Codecubicle\awdax\.env`: no `PROXY_SHARED_SECRET` line.
- Only when you need them, in the same `.env`: `AWDAX_ALLOW_PRIVATE_URLS=1` (scrape a page on your own machine) and `AWDAX_LEGACY_API=1` (old page at port 8000).
- Run from the right folder; another copy of the app was holding port 5174 earlier today:
  - Backend: `cd X:\Hackathons\Codecubicle\awdax; .venv\Scripts\python.exe app.py`
  - Frontend: `cd X:\Hackathons\Codecubicle\awdax\Frontend; npm run dev:agent`
  - If a port is busy, find who holds it: `Get-CimInstance Win32_Process -Filter "ProcessId=$((Get-NetTCPConnection -LocalPort 5174 -State Listen).OwningProcess)" | Select CommandLine`

---

## What was fixed today

### Security

| Fix | Audit IDs |
|---|---|
| Forged sign-ins refused: with the proxy secret set, identity comes only from the proxy (or a verified token); forged tokens, wrong secrets and no identity get 401; the shared "anonymous" user is gone | BE-01, BE-03 |
| The old pre-React API in `app.py` (no per-user checks; any account could read or stop other users' jobs) answers 404 | BE-02 |
| The scraper can no longer be pointed at internal addresses, cloud metadata or `file://`; every redirect hop is checked; the regulatory PDF download is guarded too | BE-04 |
| Sign-out clears the stream cookie (the next person on a shared computer could read your chats) | UX-04 |

### Reliability and data

| Fix | Audit IDs |
|---|---|
| Resume and Retry actually restart work | UX-01 |
| Pause and Delete during a first run are respected; a deleted chat no longer comes back | UX-02 |
| A new message stops the previous live loop (it ran forever before) | BE-06 |
| Runs capped at 4 total and 2 per user (`AWDAX_MAX_RUNS`, `AWDAX_MAX_RUNS_PER_USER`); over the cap the API answers 429 before anything is stopped or cleared | BE-07 |
| Websocket threads no longer pile up on finished chats | UX-05 |
| A rename or pause during a run is no longer undone by the run | UX-07 |
| Prompts capped at 2,000 characters, titles at 80 | UX-09 |
| A stuck live-socket handshake falls back after 10 s | FE-14 |

### Frontend resilience and performance

| Fix | Audit IDs |
|---|---|
| Error boundaries: a crash shows a Reload / Back to home card instead of a white page; the sidebar stays usable | FX-01 |
| An open tab after a deploy reloads once instead of going blank | FX-02 |
| The live view reconnects after a backend restart or expired cookie | FX-03 |
| A saved answer for a deleted column shows a "no longer in the data" card instead of crashing the chat | FX-04 |
| Polling only while a run works (finished chat: 8 to 2 dataset fetches in 35 s); pause/resume 4 requests to 1; the chat list no longer rebuilds every chat's table | UX-03, UX-10, UX-12 |
| No false "Waiting to start"; fake Re-score hidden; old title migration stops retrying 404s | UX-08, UX-11, UX-13 |

### Tutorial and UI

- Guided spotlight tours removed (including the landing page); replaced by a first-run tutorial video with Mute, Skip, captions, and a "Watch tutorial" button.
- The video was re-encoded to standard H.264 (`yuv420p`) with a VP9 WebM fallback, because one Windows browser refused the first file. The dialog now always fits the screen, and a compact card with "Open the video in a new tab" replaces the black box when nothing can play.
- The landing page no longer scrolls sideways on phones.

---

## Known limits of the fixes

- **Chrome and the SSRF guard:** DNS rebinding isn't covered, and Chrome navigations after the first page load are only checked on the final URL.
- **One untested piece:** the Vite `vite:preloadError` handler is covered only by a unit test, so check it once on a production build.

### How to check the preload handler (10 minutes)

```powershell
cd X:\Hackathons\Codecubicle\awdax\Frontend
npm run build; npm run preview      # open the printed URL, go to /app, leave the tab open
# in a second terminal: change any text in src, then
npm run build                       # new hashed chunk names
```

Back in the open tab, navigate to another page. It should reload once and work, not go blank. The test needs `vite preview` to be serving the new `dist/`; restart preview if it doesn't pick it up.

---

## Not done

- **BE-05** (live mode on by default, so uncapped AI spend): this changes the product, so it needs your decision. The run cap limits the damage in the meantime.
- **BE-08** (a performance change) and **BE-09** (deployment): BE-09 means running under gunicorn with one worker and pinned dependency versions, which is yours to do.
- **The Medium and Low findings** (`docs/audit/PRODUCTION_AUDIT.md`).

---

## What I advise, and how

### 1. Merge and deploy (first)

1. Open a pull request from `integration/oct-02-hardening` into `main` (`main` gained one commit today, so let GitHub show any conflict).
2. After merging: set the secret (above), deploy the frontend, restart the backend on the new code.
3. Do **one real end-to-end run** (a real prompt, real AI keys) and confirm it reaches "Run complete". This is the one thing nobody has seen yet.

### 2. BE-05: live mode (decide, then small change)

Today every chat re-scrapes and calls the AI every 90 seconds until someone pauses it. Options, cheapest first:

| Option | What changes for users | Effort |
|---|---|---|
| **A. Auto-pause after 24 h without a visit** (recommended) | Tracking keeps working for chats people actually look at; abandoned chats stop costing money; one click resumes | S–M |
| B. Live off by default, "Keep tracking" toggle when starting a chat | Clear and cheapest, but most runs become one-shot | S |
| C. Cap live loops per user (e.g. 3); oldest pauses when a 4th starts | Predictable cost; may surprise users | S |

### 3. BE-09: run the backend properly

- **Linux host:**
  - Add `gunicorn` to `requirements.txt` and run it with **exactly one worker**, because run state lives in the process:
    `gunicorn -w 1 -k gthread --threads 32 --timeout 120 -b 127.0.0.1:8000 app:app`
  - Also run `recover_interrupted_runs()` at startup in the app factory, not only under `__main__`.
- **Windows host:** gunicorn doesn't run on Windows. Use `waitress` instead:
  `waitress-serve --threads=32 --listen=127.0.0.1:8000 app:app`
  WebSockets aren't served there, but production already falls back to the event stream.
- **Pin versions:** run `pip freeze > requirements.lock` from a working venv, deploy with `pip install -r requirements.lock`, and keep `requirements.txt` as the human list.

### 4. BE-08: take the AI off read paths

- In `awdax_api/dataset_export.py`, call `merge_records(..., use_ai=False)` on GET paths and keep the AI merge for the end of a run only.
- Send streamed rows as deltas instead of rebuilding the 5,000-row table for each row.
- Measure before and after with one live run (time per GET `/dataset`).

### 5. Medium items, in this order

| # | Item | Why first |
|---|---|---|
| 1 | BE-13 rows lost after AI merge (81–120 rows) | silent data loss |
| 2 | BE-14 Gemini timeout; one 401 disables NVIDIA until restart | runs hang for minutes |
| 3 | FX-09 security headers (`Frontend/public/_headers`: CSP, `frame-ancestors 'none'`, Referrer-Policy) | cheap, closes clickjacking; test the CSP on a preview deploy first |
| 4 | BE-16 deleting a chat keeps its scraped data | privacy |
| 5 | BE-18 "live" shown after a restart; BE-11 live events dropped after first pass | confusing status |
| 6 | FX-07 projects report polls every chat every 15 s | Cloudflare quota |
| 7 | FX-05 / FX-06 profiling cost; CSV over ~120k rows crashes | performance |
| 8 | FX-16 tests for exports, SQL escaping, `runQuery`; one Playwright smoke test | keeps the above from regressing |

Low items (timeouts, N+1 list query, raw error text, `/ready`) can follow in one small batch.
