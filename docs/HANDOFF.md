# Handoff: UI polish, demo replays, faster discovery (3 October 2026)

`feat/new-chat-compact` was merged as PR #23 (up to `39f10d3`). Branch `fix/polish-and-run-speed` holds the rest:
`dcc8308` (phones demo card, pushed after #23 merged), `80f7a22`, `c76358b` and this handoff.

## Done

| Area | What changed | Commit |
|---|---|---|
| App | New chat fits a 1536×735 laptop without scrolling; resizable sidebar (220–420 px, remembered) | 67b6f9e |
| App | No shortcut strip; + upload button inside the prompt box; normal-width headline | 2ca6297 |
| Chat | User message on the right edge; ⋯ menu (two-step delete); top-3 sources; full-width ask section | b587a21, 0a369a3, 588c100 |
| Chat | Run card is one ThoughtLine (live clock shown only when true); replays paced at 2 s+ per beat | a88b474, 39f10d3 |
| Live | `starting` / `live_scraping` phases no longer read "Waiting to start" | fb90f4b |
| Landing | Hero's sample run reaches its first source page ~2.5 s sooner (design unchanged) | 3ef8df5 |
| Demo | Sample cards replay real recorded runs (`/app/demo/<slug>`, `public/demo/*.json`): phones 9 rows, cars 29 rows | e7d2249, dcc8308 |
| App | Audit fixes: working placeholder, `/app/sample` removed, no stale "Reading now", plain headings, phone layout | 80f7a22 |
| Backend | Discovery inspects 3 sources at a time; default source cap 10 → 6 | c76358b |

## Verified (3 Oct)

- Frontend `verify.mjs` PASS (lint, types, build, 176 tests); no raw hex outside `tokens.css`. Backend: 172 unittest OK.
- Browser (Playwright): 9 routes × 1536×735 and 375×812, 0 console errors, no sideways scroll; `/app/sample` redirects to `/app`.
- Real runs, local, NVIDIA + Chrome, same prompt: schema at 268 s (was ~742 s); first pass complete at 732 s with 27 sourced
  rows (was: up to date at 1503 s, never "complete" in 30 min). A 2.5-min smoke run on the final code inspected 3 sites at once.

## Needs attention (3 Oct)

1. **Merge and deploy** `fix/polish-and-run-speed`. It carries `dcc8308` (phones card), which is not in `main` yet. Restart the
   backend for the faster discovery.
2. **Server load.** A run now uses up to 3 headless Chromes and 3 parallel LLM calls (`DISCOVERY_INSPECT_WORKERS`, default 3). On a
   small host, or with several users at once, that can run out of memory or hit NVIDIA 429s (a 300 s cooldown per model). Set it to 2
   or 1 there.
3. **Dead `.env` names.** `MIN_VALIDATED_SOURCES`, `MAX_SOURCES_TO_INSPECT`, `MAX_DISCOVERY_SEARCH_ROUNDS`,
   `MAX_DISCOVERY_ATTEMPTS`, `MAX_TOTAL_URLS_INSPECTED`, `BROWSER_TIMEOUT_MS`, `BROWSER_MAX_RELATED_LINKS`,
   `LIVE_REFRESH_INTERVAL_SECONDS` and `LIVE_ERROR_RETRY_SECONDS` are read nowhere. The real knobs: `DISCOVERY_MAX_SOURCES` (6),
   `DISCOVERY_INSPECT_WORKERS` (3), `DISCOVERY_MAX_INSPECT_ATTEMPTS` (40) and `NVIDIA_TIMEOUT_SECONDS` (90).
4. **Runs still take ~12 min.** The scrape still visits sources one at a time (about 6 min of a run). It is the next speed win, but it
   writes to the database as it goes, so it needs care.
5. **Result quality.**
   - "Reference" rows (a model name, every other column blank) inflate counts: 55 of 82 in the speed test.
   - History and time-series prompts come back thin or junk: EV monthly sales gave model names as months; RBI repo rate gave 1 row.
   - Runs are flaky: the phones prompt gave 0 rows once, then 9.
6. **Demo replays** were recorded locally on 3 Oct. They show real times with no "recorded" label (owner's choice). To re-record, run
   `Frontend/scripts/record-demo.mjs`, then `build-replay.mjs`. Check the rows before shipping.
7. **Tutorial video** still shows the old start screen. Re-record it with a real voice-over (owner: later).
8. **Small leftovers.**
   - A chat's heading reads "Untitled chat" for a moment while it loads (pre-existing).
   - The source cap ignores `intent.max_sources`.
   - `CallChip` is now used only by the dev gallery.
9. Old item 4 below (the landing page scrolling sideways at 375 px) did not reproduce on 3 Oct.

---

# Handoff: stability pass (2 October 2026)

Branch `fix/stability-pass` (from `main` @ `6fc90ba`). Read `AGENTS.md`, then `docs/audit/README.md`.

## Done (committed on this branch)

| Area | What changed | Commit |
|---|---|---|
| Audit | ZIP claims checked, frontend race findings, plan (`docs/audit/`) | 20d02b4 |
| Backend | NVIDIA LLM client (`llm_client.py`), per-user scoping on every `/api/instances/<id>` route, fail-closed JWT, optional `PROXY_SHARED_SECRET`, SQLite WAL, flags before thread start, eGazette only when asked | ff72489 |
| Frontend | No false "chat deleted", no orphan "Untitled chat", ordered list reads, short error text | 416d77e |
| Frontend | Live view: one state source, snapshot gate (no vanishing rows, no false "new rows" alerts) | 5dbfff7 |
| Frontend | Microphone never outlives the pill; auth gate can't hang | 99d0a25 |
| Frontend | One project-poll cycle, atomic file rename, proxy JWKS memo + shared secret | eb02f3a |
| Backend | `LLM_MODEL` "openai/<org>/<model>" accepted; interrupted runs marked failed at start; debugger off | 1cb14a1 |
| Backend | NVIDIA models that time out or are busy sit out a cooldown; last good model first | e65608e |

Specs for each batch: `.agent/specs/`. Review findings were fixed before commit.

## Verified

- Frontend `verify.mjs`: lint, types, build, tests PASS (77 tests). Backend: 36 unittest OK.
- Local end-to-end (backend + `npm run dev:agent`, real NVIDIA keys): chat titled from the prompt instantly; run starts;
  planning, discovery and source inspection stream live into the page (CarWale, CarDekho, 91Wheels, ZigWheels, Wikipedia,
  CarTrade, Autocar India found; eGazette not used); another user gets 404 on someone else's chat; a restart marks the cut-off run
  "Run interrupted" instead of running forever. All app routes render with 0 console errors at 1536×864 and 375×812.

## Not verified / open

1. **No run reached "Run complete" locally.** NVIDIA's hosted API was slow (90 s timeouts, 503s); after ~35 min the run was still
   discovering. The cooldown commit (e65608e) should cut that a lot. Re-run once with the backend restarted on this branch.
2. **Production `awdax.synapical.com` serves an old frontend build** (no goal passed on create → "Untitled chat"). Deploy this branch.
   It also uses a different Supabase project (`dwxszgmbipjpjmeidlgh`) than `awdax.pages.dev` (`allwrzhdjodscxztcewu`).
3. **Deploy config** (owner): restart the backend on this code; set `PROXY_SHARED_SECRET` to the same value on Cloudflare Pages and the
   backend; leave `SUPABASE_JWT_SECRET` unset (tokens are ES256). `Frontend/.github/workflows/deploy.yml` never runs in this monorepo.
4. Landing page `/` scrolls sideways at 375 px (pre-existing; UI/UX pass).
5. Open product decisions: per-user browser storage for uploaded files (FE-13 / task A7); range midpoints in totals (`233fb40`).
6. Branch-only tour commits `825b086`, `861f1c9`, `92130ba` not cherry-picked yet (see `docs/audit/REMEDIATION_PLAN.md` Track C).

## Run locally

Backend: `.venv/Scripts/python.exe app.py` (port 8000; needs `.env` with `NVIDIA_API_KEY`, `NVIDIA_API_BASE`, `LLM_MODEL`).
Frontend: `cd Frontend && npm run dev:agent` (port 5174, no sign-in; needs `Frontend/.env.local` with the two `VITE_SUPABASE_*` values).
