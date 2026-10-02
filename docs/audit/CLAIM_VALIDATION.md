# ZIP claim validation

Source: `##Documentation_Fixes.zip` (5 Markdown reports, 33 screenshots), checked against
`main` @ `6fc90ba` and `origin/frontend` @ `92130ba` on 2 October 2026.
Verdicts: **TRUE** · **PARTIAL** (part holds, part does not) · **FALSE** · **UNPROVEN** (cannot be decided from code; needs logs or production access).

## Branch facts the reports get wrong

The reports say most UI work sits on an unmerged "local `frontend` branch". In fact:

- `frontend` is pushed (`origin/frontend`), not local-only.
- 14 of the 19 "frontend branch" commits are **already on `main`** through ten `merge: frontend -> main` commits
  (tour `1b1af96`, `cdc0d7f`, `a553d9c`, `165978d`; charts `aba6e51`, `ba44bb3`, `06ee91c`; UI `813c691`, `7ff9c7d`,
  `2a78d45`, `4e7e74a`, `7303003`; repo `3ddd8ef`, `a23fc4a`).
- Only **five** commits are branch-only: `233fb40` (range parsing), `825b086`, `861f1c9`, `92130ba` (tour), `c590915` (SQLite/concurrency).
- `git merge-tree main origin/frontend` reports conflicts in `ui_sessions.py`, `awdax_api/routes.py`
  and `Frontend/src/app/chat/NewChat.tsx`. `app.py` merges cleanly (the reports predicted it would conflict).

So "merge `frontend` and the tour, smooth charts and donut fix go live" is wrong: those are already on `main`.

## Claim table

| # | Claim (source) | Verdict | Evidence |
|---|---|---|---|
| C1 | Sessions are "strictly scoped to `user_id`"; one user can't view another's chats (1_Code_Changes) | **FALSE** | Only list/create/delete pass a user. Every per-instance route loads by ID alone: `awdax_api/routes.py:65` GET, `:73` PATCH, `:105`/`:113` messages, `:145` dataset, `:176` dashboard, `:184`–`:207` live/stream, `:243`–`:280` sources/stats/rescore/graph, `:292` WebSocket, all via `session_store.py:29` → `get_session(id)` with no user. DELETE stops the other user's live job (`routes.py:96`–`:100`) before its scoped delete fails. |
| C2 | Backend "cryptographically verifies" Supabase JWTs with PyJWT (1_Code_Changes, screenshots) | **FALSE in effect** | `auth_helper.py:28`–`:31`: a failed signature check logs a warning and **decodes without verification**. No secret → unverified (`:33`). This project's Supabase tokens are **ES256** (the proxy accepts nothing else: `Frontend/src/server/jwt.ts:66`), and an HS256 `SUPABASE_JWT_SECRET` cannot verify ES256. So, by reading the code, real tokens would **always** take the unverified path (not run against a live token). `auth_helper.py:9`–`:11` trusts any caller's `X-User-Id` header before looking at the token. Anyone who can reach the backend origin directly can pick any user ID. |
| C3 | Proxy forwards `Authorization` and `X-User-Id` (f59f7a9) | **TRUE** | `Frontend/src/server/proxy.ts:66`–`:75`. The proxy sets `x-user-id` from verified claims and never forwards a client-supplied one (allowlist `FORWARD`). The weakness is the backend trusting that header from anyone, not the proxy. |
| C4 | "Not a data leak" (screenshot `123347`, earlier assistant) | **FALSE** | New accounts saw other people's chats: that is cross-user exposure. On `main` it can still happen: legacy rows default to `user_id='anonymous'` (`ui_sessions.py:43`), and any request whose identity resolves to `anonymous` (no token, decode error) shares that bucket. |
| C5 | "Old chats are safe, assigned to `anonymous`" (screenshot `125012`) | **FALSE as a safety claim** | It means every unauthenticated caller to the origin lists all legacy chats. |
| C6 | 524s are caused by an SQLite deadlock (3_Current_Site, issues_and_fixes) | **UNPROVEN, likely incomplete** | All `ui_sessions` access is serialized by one process-wide `threading.Lock` (`ui_sessions.py:18`), so those threads cannot deadlock each other. SQLite's default 5 s busy timeout makes a locked DB **fail fast** (HTTP 500), not hang 100 s. A 524 means the origin sent nothing for 100 s. Other candidates visible in code: the Flask **dev server with `debug=True`** in use (`app.py:739`); WebSocket handlers blocking forever on `sub.get()` with no timeout (`routes.py:301`); `/api/events` polling every 50 ms (`app.py:366`); and the origin being a tunnel to one PC. Needs backend logs to decide. |
| C7 | WAL + 30 s busy timeout (`c590915`) is "the exact cure" for the 524s | **FALSE as stated** | WAL lets readers run beside one writer. It does not fix an unreachable origin, thread exhaustion, or the frontend showing HTML. A 30 s busy timeout can **lengthen** a stall. The commit's other changes help: closing connections before PDF/LLM calls (`RegulatoryFeed.py` diff) and setting running flags before `t.start()`. |
| C8 | Frontend "injects raw HTML" into the sidebar (3_Current_Site) | **PARTIAL, and it points at a deployment question** | The client shows a non-JSON error body **as text**: `client.ts:16`–`:23` returns the raw body and `HistoryList.tsx:34`, `:41` renders it. React escapes it, so there is no HTML execution or XSS. But the Pages proxy already turns any non-JSON upstream 5xx into a short JSON message (`Frontend/src/server/proxy.ts:91`). A 524 page can reach the sidebar only if the browser bypasses that proxy (a build with `VITE_API_BASE_URL` set to a Cloudflare-fronted backend), or in local dev. **No 524 screenshot is in the ZIP.** If production really shows it, `awdax.synapical.com` is not using the proxy, so the backend's trust in `X-User-Id` (C2) is directly exposed. |
| C9 | Merging `frontend` removes the HTML from the sidebar (issues_and_fixes) | **FALSE** | No branch commit touches `client.ts` error handling. It needs its own frontend fix. |
| C10 | Pushing `main` makes "CI/CD automatically deploy the fixed backend" (3_Current_Site) | **FALSE for this repo** | No root `.github/workflows`. `Frontend/.github/workflows/deploy.yml` is ignored by GitHub inside a monorepo, and it targets `phase-1`, not `main`. Nothing deploys the Python backend. How `awdax.synapical.com` is built and hosted is **UNPROVEN**. |
| C11 | Title race fixed by atomic `update_session_title` (2_Caught_Issues) | **PARTIAL** | `c590915` keeps a custom title only when the stale snapshot's title is generic (`DEFAULT_TITLES`). Since auto-naming, a running job's snapshot already holds the derived title, so a rename during a run can still be overwritten. Other fields (messages, sources, run events) still lose updates through whole-payload writes (`ui_sessions.py:157`–`:172`). |
| C12 | Running flags set too late, so "Run complete" at 0 s (screenshots `234059`–`234111`) | **TRUE on `main`, fixed on branch** | `RegulatoryFeed.py:1017` starts the thread, but `is_running = True` is set inside it (`:1021`). `scraper.py:1209` adds to `_running_jobs` inside `_run_all`. `orchestrator.py:81`–`:93` can poll before either is set and finish at once. `c590915` sets both before `start()`. |
| C13 | Slow network/LLM calls are made while holding DB cursors (same screenshots) | **TRUE on `main`, fixed on branch** | Pre-`c590915` `_ensure_pdf_text`/`_generate_summary_for` kept the connection open across downloads and LLM calls. |
| C14 | `/api/events` 50 ms loop saturates worker threads | **PARTIAL** | The 50 ms timeout (`app.py:366`) wastes CPU. Thread occupancy is per open connection whatever the timeout, so raising it to 1 s cuts CPU, not threads. |
| C15 | Normalisation "actively trims outliers from the mean" (`233fb40`) | **FALSE** | `trimmedMean` exists in `decimal.ts` and has a test, but `git grep` on `origin/frontend` finds **no caller**. Averages are unchanged. |
| C16 | Ranges like `₹11.45 - ₹26.95 Lakh*` become usable values (`233fb40`) | **TRUE on branch only, needs a product decision** | `parse.ts` turns ranges into midpoints marked `approx`. That is not on `main`. Risks: "Total price" then sums midpoints. Hyphenated non-ranges (phone numbers, "2024-25", model codes) may parse as ranges, and the branch has no tests for that. |
| C17 | "21 rows used → 57+" after the fix (screenshots `215124`–`215151`) | **UNPROVEN** | The 68-row EV dataset is not in the ZIP, so this cannot be reproduced. |
| C18 | Donut overflow fixed (`aba6e51`) | **TRUE, already on `main`** | The fix caps the legend list height (`Donut.tsx`, 2 lines). The "charting library" explanation is wrong: charts are hand-built SVG. |
| C19 | Chat auto-naming (`067c019`) | **TRUE on `main`** | `NewChat.tsx:68` passes the goal; `routes.py:128`–`:131` renames still-untitled chats. Chats created earlier stay "Untitled chat". |
| C20 | "17/17 backend tests", "39/39 frontend tests" pass (screenshots) | **Frontend re-checked; backend not run** | Our baseline gate on `main`: lint, types, build and tests all PASS (`.agent/evidence/baseline-verify.json`). Backend tests were not run (not in our scope). |
| C21 | Production at `awdax.synapical.com` is down with 524s right now | **UNPROVEN** | No production access was used, and none of the 33 screenshots shows a 524. Screenshots are dated 1–2 Oct. |

## Bottom line

1. The **frontend** problems the ZIP describes are real but come from different causes than it says: the HTML-as-text error (FE-07)
   and the stale/racing list state (FE-01, FE-02) need **frontend** fixes. A backend merge does not provide them.
2. The **security** claims are the most wrong. Isolation is incomplete and the backend accepts forged identities.
   This matters more than the 524s.
3. `c590915` has real backend value (WAL, no DB handles held across network calls, flags set before threads start),
   but it is not a proven 524 cure and conflicts with `main` in three files.
4. `233fb40` should not merge as is: its "trimmed mean" is unused and range midpoints change what totals mean.

## Out of our hands (needs the owner)

- The backend is **read-only for this agent** (owner's standing rule). Every backend item above goes to the backend
  owner or needs explicit approval. See REMEDIATION_PLAN.md, track B.
- Production logs, hosting of `awdax.synapical.com`, the backend origin's public reachability, and the Supabase JWT key type (HS256 secret vs ES256 signing keys) all need owner access.
