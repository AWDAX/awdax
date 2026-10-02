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
