# AWDAX production audit

**Date:** 2 October 2026 · **Audited state:** `integration/oct-02` (all of today's fixes) · **Lens:** production breakers, security, reliability, code quality
**Method:** two independent read-only reviews (backend, frontend), each claim checked in code; the two Critical findings and three of the High findings were re-checked by hand. `npm audit` and `pip-audit` run. Frontend lint, tests and build run.
**Status note (added when saved):** `origin/main` has since gained the tutorial video and first-run gating, which resolves **FX-08**. Everything else below was still open when this was written. Fix status is tracked in the last section.

## Verdict

**Not ready for public traffic. Fine for a closed beta once the two Critical items are fixed.**

| | Grade | In one line |
|---|---|---|
| Frontend | **B−** | Strict types, small files, careful race handling, clean lint, 90 passing tests. Not resilient in production: one render error or one deploy can blank the screen. |
| Backend | **D** | The `/api/instances` layer is solid and tested, but it sits on an older single-user core: forgeable identity, an old unprotected API, no limits on threads, Chrome or AI spend, and it runs on Flask's development server. |

## Critical

| ID | Problem | Where | Effort |
|---|---|---|---|
| **BE-01** | **Anyone can sign in as anyone.** With `SUPABASE_JWT_SECRET` unset, the backend reads the user ID from a login token without checking its signature. Anyone who reaches the backend origin directly can forge any user. With no proxy secret, a bare `X-User-Id` header is enough. | `auth_helper.py:46-48` | M |
| **BE-02** | **The old API is still live with no per-user checks.** About 17 legacy routes in `app.py` (`/api/events`, `/api/feed`, `/api/scrape/*`, `/api/sessions*`, `/api/prompt`, `/api/discover`, ...) are reachable by any signed-in Google account. `/api/events` streams everyone's scraped data; `PATCH /api/sessions/<own>` with someone else's `job_id` makes the protected endpoint serve their data. The React app uses none of these routes. | `app.py:146-688` | S |

## High

| ID | Problem | Where | Effort |
|---|---|---|---|
| BE-03 | A request with no token becomes user `"anonymous"`, which owns every legacy chat. | `auth_helper.py:36`, `ui_sessions.py` | S |
| BE-04 | **SSRF.** The scraper fetches URLs that users or the AI choose, with `requests` and headless Chrome, with no IP checks. Redirects to `169.254.169.254` (cloud metadata) or `file://` work. | `scraper.py:391`, `inspector.py:169`, `discovery.py:124` | M |
| BE-05 | **Unbounded AI spend.** Every chat becomes live by default and rescrapes every 90 s with AI extraction and merging until someone pauses it. | `routes.py:150`, `scraper.py:898` | S |
| BE-06 | A new message to a live chat leaves the old live loop running forever, orphaned. | `routes.py:157-163` | S |
| BE-07 | No limit on concurrent runs or Chrome instances; ten users at once can run the host out of memory. | `orchestrator.py:229`, `scraper.py:1083` | M |
| BE-08 | Every streamed row rebuilds the whole 5,000-row table; read requests can trigger a multi-minute AI merge that stalls live updates for everyone. | `live_bridge.py:366`, `dataset_export.py:41` | M |
| BE-09 | Production runs Flask's development server: no WSGI server, no timeouts, unpinned dependencies. | `app.py:744`, `requirements.txt` | M |
| FX-01 | **No error boundary anywhere.** Any render error shows a white page with no recovery and no error reporting. | `main.tsx`, `AppRoot.tsx` | S |
| FX-02 | Tabs open during a deploy go blank (old chunk → HTML 200). A build missing `VITE_SUPABASE_*` also blanks `/login` and `/app`. | `App.tsx:6-8`, `supabase.ts:6` | S |
| FX-03 | The live view freezes after any backend blip: a non-200 closes an `EventSource` permanently and nothing reopens it. The U2 polling gate makes it worse, because run status only arrives over that stream. | `useLiveStream.ts:228-256` | M |
| FX-04 | A saved answer whose column index no longer exists throws on render, on every visit, until site data is cleared. | `useAnswers.ts:31`, `aggregate.ts:173` | S |

## Medium

| ID | Problem | Effort |
|---|---|---|
| BE-10 | A live run can post "Run complete" with 0 rows (race; unconfirmed). | S |
| BE-11 | After the first pass, live-cycle events are dropped. | S |
| BE-12 | Concurrent writes still overwrite `run_events` and `sources` (only title, pause state and archived are protected). | M |
| BE-13 | Tables of 81–120 rows lose up to 40 rows after the AI merge. | S |
| BE-14 | Gemini fallback has no timeout; one AI call can take 6+ minutes; one 401 turns NVIDIA off until restart. | S |
| BE-15 | The discovery fetch reads the full response into memory and retries every host with TLS checks off. | S |
| BE-16 | Deleting a chat leaves its scraped data in the database. | S |
| BE-17 | `max_pages="abc"` gives a 500; no request-size limit. | S |
| BE-18 | After a restart, chats say "live" but nothing is running. | S |
| FX-05 | Each 5 s poll re-profiles 5,000 rows twice (170–315 ms measured). | M |
| FX-06 | A CSV over ~120,000 rows crashes with "Maximum call stack size exceeded". | S |
| FX-07 | The projects report polls every chat every 15 s; can exhaust the Functions free quota. | M |
| FX-08 | ~~Tutorial popup opens with no video.~~ **Resolved on `main`:** the video is committed and the popup opens only once the video can play. | S |
| FX-09 | No security headers (CSP, clickjacking protection, Referrer-Policy). | S |
| FX-16 | The riskiest code has no tests: exports, SQL escaping, `safeNext`, `runQuery`, live-stream wiring; no end-to-end tests. | M |

## Low / Info

- **Backend:** BE-19 Chrome has no page-load timeout. BE-20 chat list does N+1 queries. BE-21 raw exception text goes to users. BE-22 `/ready` checks nothing. No backend dependency is version-pinned.
- **Frontend:** FX-10 a crafted `next=` link can blank the page. FX-11 WebSockets can never connect through the proxy (2–4 s wasted per chat open). FX-12 the proxy's backend request has no deadline. FX-13 "new rows" toasts can stack. FX-14 source links are not scheme-checked (React blocks `javascript:`, so not exploitable). FX-15 the `api` layer imports from `app`; 4 unused API methods. FX-17 deploy branch (`phase-1`) and Safari 16.4+ requirement unconfirmed.
- **Dependencies:** 2 moderate npm advisories (`uuid` via `exceljs`), not exploitable here. `pip-audit`: none found.

## What is working well

- Strict TypeScript, almost no `any`, every frontend file under 300 lines; exact decimal maths; no dangerous HTML sinks; CSV/TSV exports neutralise formulas; PKCE login; disciplined race handling.
- All SQL parameterised; every `/api/instances` route, the WebSocket and the SSE stream check the user, with tests; lifecycle fixes tested; no secrets in the repo.
- The Pages proxy verifies ES256 tokens, fails closed, and cannot be spoofed with `x-user-id` from the browser.

## Recommended order

1. BE-02: delete or gate the old `app.py` routes.
2. BE-01 + BE-03: verify identity properly; no `"anonymous"`.
3. BE-05 + BE-06 + BE-07: live mode opt-in, stop old loops, cap runs.
4. FX-01 + FX-02 + FX-03: error boundaries, reload on stale chunk, reconnect the live stream.
5. BE-04: SSRF guard.
6. BE-09 + FX-09: gunicorn with one worker and pinned dependencies; security headers.
7. The Medium items.

## Fix status

All batches below are merged on `integration/oct-02-hardening`: 151 frontend tests, 165 backend tests, lint clean, build passes,
and the real backend was exercised over HTTP in strict mode (forged token, user header without or with a wrong secret, no identity: 401;
another user's chat: 404; old routes: 404; valid proxy headers: 200/201; over-long prompt: 400).

| Batch | Items | Branch | State |
|---|---|---|---|
| P1 | BE-01, BE-02, BE-03 | `fix/p1-auth` | done. **BE-01 only takes effect once `PROXY_SHARED_SECRET` is set on the backend and on Pages.** |
| P2 | BE-06, BE-07 | `fix/p2-runs` | done (cap 4 total / 2 per user, 429 before any side effect) |
| P3 | BE-04 | `fix/p3-ssrf` | done. Limits: DNS rebinding; Chrome navigations after the first load are checked on the final URL only. Local scraping of localhost needs `AWDAX_ALLOW_PRIVATE_URLS=1`. |
| F1 | FX-01, FX-02 | `fix/f1-boundary` | done. `vite:preloadError` is unit-tested only; verify once on a production build. |
| F2 | FX-03 | `fix/f2-sse` | done |
| F3 | FX-04 | `fix/f3-answers` | done |
| — | BE-05 (live mode on by default) | | open: changes the product, needs an owner decision |
| — | BE-08, BE-09 | | open: larger performance change; deployment change (gunicorn with one worker, pinned versions) |
| — | Medium and Low items | | open |

**Not verified:** what production actually runs (whether `PROXY_SHARED_SECRET` or `ALLOWED_EMAILS` is set, whether the backend origin is publicly reachable, which branch Pages deploys), the regulatory-feed internals beyond SSRF, and behaviour under load. BE-01 and BE-02 are exploitable either way.
