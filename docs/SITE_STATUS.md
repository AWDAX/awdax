# AWDAX site status

**As of:** 2 October 2026 · **Code state:** branch `integration/oct-02-hardening` (on top of `main` @ `082e0fe`)
**Not yet merged to `main`, not yet deployed.** Production (`awdax.synapical.com`, `awdax.pages.dev`) runs whatever was last deployed, not this branch.

## Does the site work properly now?

**The code is in much better shape and holds up in every check we could run. It is not proven to work in production, because it has not been deployed and no full run has been tested end to end with the real AI services.**

| Question | Answer |
|---|---|
| Can the pages load and render? | **Yes.** Every route renders at desktop (1536 px) and phone (375 px) width with no page errors and no sideways scroll. |
| Can one user read another user's data? | **Not any more, once `PROXY_SHARED_SECRET` is set** on the backend and on Pages (see "Needed from you"). Checked over real HTTP. |
| Can a bug blank the whole screen? | **Much less likely.** Error boundaries now catch a render error, and a stale chunk after a deploy reloads once. |
| Does the live view survive a backend restart? | **Yes** in a browser test with a mocked backend. Not tried against the real one. |
| Does a run finish with real data? | **Unknown.** No run reached "Run complete" locally (the AI provider was slow). Needs one real run. |
| Is it ready for public traffic? | **No.** Fine for a closed beta once deployed with the secret set. Open items below. |

## What was checked, and how

| Check | Result |
|---|---|
| Frontend lint | clean (0 problems) |
| Frontend tests | **151 of 151 pass** |
| Frontend production build | passes |
| Backend tests | **165 of 165 pass** |
| Real backend over HTTP, production setting on | forged login token **401**; user header with no or a wrong secret **401**; no identity **401**; valid proxy headers **200 / 201**; another user's chat **404**; old routes (`/api/events`, `/api/feed`, `/`, `PATCH /api/sessions`) **404**; a 2,001-character prompt **400** |
| Browser, all routes, desktop and phone | renders, no page errors |
| Browser, tutorial video popup | opens on first visit, muted fallback, Unmute, Skip, replay, 21 caption cues (tested with a playable copy of the same video, because the test browser cannot decode H.264) |
| Browser, live stream with a mocked backend answering 503 twice | stream reopens (1 request became 3), phase recovers |
| Browser, saved answer pointing at a deleted column | no white screen, "no longer in the data" card with a remove button |
| Dependency audit | backend: none found; frontend: 2 moderate (`uuid` via `exceljs`), not exploitable here |

**Not checked:** a deployed build on Cloudflare Pages, a real signed-in Google session, a complete run against the real AI providers, behaviour under load, the `vite:preloadError` handler on a production build (unit-tested only), and any production request.

## What was fixed (all merged on the integration branch)

| Area | Fix | Audit items |
|---|---|---|
| Security | Forged identities refused (strict mode); no shared "anonymous" user; the old unprotected API answers 404 | BE-01, BE-02, BE-03 |
| Security | The scraper cannot be pointed at internal addresses or `file://`; redirects checked at every hop | BE-04 |
| Reliability | A new message stops the previous live loop; runs capped at 4 total and 2 per user (429 before any side effect) | BE-06, BE-07 |
| Reliability | Pause and Delete during a first run are respected; deleted chats stay deleted; Resume and Retry restart work; websocket threads exit; user edits survive a run | UX-01, 02, 05, 06, 07 |
| Resilience | Error boundaries; reload once on a stale chunk after a deploy | FX-01, FX-02 |
| Resilience | The live view reconnects after a backend restart or expired cookie | FX-03 |
| Resilience | A saved answer for a missing column no longer crashes the chat | FX-04 |
| Performance | Polling only while a run is working (finished chat: 8 to 2 dataset fetches in 35 s); pause/resume 4 requests to 1; the chat list no longer builds every chat's table | UX-03, 10, 12 |
| UX | Sign-out clears the stream cookie; no false "Waiting to start"; no fake Re-score; landing page fits at 375 px; tours replaced by a first-run tutorial video | UX-04, 08, 11 |

Earlier work already on `main`: the stability pass (NVIDIA client, per-user chats, WAL, interrupted runs), race and lifecycle fixes FE-01 to FE-12 and N4/N5, per-account file storage, and the tutorial video asset.

## Needed from you (the fixes do not protect production until these are done)

1. **Set `PROXY_SHARED_SECRET`** to the same value on the backend and on Cloudflare Pages. Without it the backend stays in permissive mode and the forgery hole stays open.
2. **Deploy** this branch (merge to `main`, then deploy the frontend and restart the backend). Production currently serves older code.
3. **Local development:** leave `PROXY_SHARED_SECRET` unset in your local backend `.env` (otherwise every local call returns 401). Scraping `localhost` needs `AWDAX_ALLOW_PRIVATE_URLS=1`; the old page at `http://127.0.0.1:8000/` needs `AWDAX_LEGACY_API=1`. Never set the legacy flag in production.
4. **Run one real end-to-end run** (backend restarted on this code) and confirm it reaches "Run complete".
5. **Decide BE-05:** live mode is on by default, so every chat re-scrapes and calls the AI every 90 seconds until paused. The run cap limits the damage; making live opt-in changes the product.

## Still open

| Item | Why it matters | Effort |
|---|---|---|
| BE-05 live mode on by default | uncapped AI spend; needs your decision | S |
| BE-08 every streamed row rebuilds the whole table; reads can trigger a multi-minute AI merge | slows live updates for everyone | M |
| BE-09 production runs Flask's development server; dependencies unpinned | no timeouts or worker control; use gunicorn with exactly one worker and pinned versions | M |
| BE-10 to BE-18 (Medium) | e.g. rows lost after AI merge for 81 to 120 rows; no Gemini timeout; deleted chats keep their scraped data; "live" shown after a restart | S to M |
| FX-05 to FX-07, FX-09 (Medium) | 5,000-row table re-profiled on every poll; CSV over about 120,000 rows crashes; projects report polls every chat every 15 s; no security headers (CSP) | S to M |
| FX-16 tests | no tests for exports, SQL escaping, `runQuery` edge cases, live-stream wiring; no end-to-end tests | M |
| Low and Info items | see `docs/audit/PRODUCTION_AUDIT.md` | S |

## Known limits of the new fixes

- **SSRF guard:** DNS rebinding is not covered; Chrome navigations after the first page load are checked on the final URL only.
- **Run cap:** counts runs, not live loops; it lives in one process, so more than one backend worker would each enforce their own.
- **Auth strict mode:** accepts identity only from the proxy headers or a token verified with `SUPABASE_JWT_SECRET`. Tokens are ES256, so only the proxy path works, which is intended. Verifying ES256 directly in Python is a possible later hardening.
- **Saved answers** are flagged stale whenever the column names change, even if their indexes would still fit.

## Where to read more

- `docs/audit/PRODUCTION_AUDIT.md`: the full audit (22 backend and 17 frontend findings, grades, order of fixes)
- `docs/audit/FRONTEND_FINDINGS.md`, `docs/audit/CLAIM_VALIDATION.md`: earlier findings and the claim check
- `docs/HANDOFF.md`: earlier handoff, run instructions
- `Frontend/docs/TUTORIAL_VIDEO.md`: how the tutorial video is wired
