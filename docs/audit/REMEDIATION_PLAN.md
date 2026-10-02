# Remediation plan

Inputs: FRONTEND_FINDINGS.md (FE-xx, N-x) and CLAIM_VALIDATION.md (Cxx). Baseline `main` @ `6fc90ba`; the gate passes there.
**Nothing below has been implemented.** The owner approves batches; agents commit on branches; the owner pushes and deploys.

## Ground rules for every batch

1. **One concern per batch, one branch per batch** (`fix/fe-<ids>`), cut from `main`. Never `git merge frontend` wholesale.
2. **Pure logic first, hook second.** Put ordering and generation rules in a small pure module with a Node test,
   like `api/liveState.ts` + `liveState.test.ts` and `api/mergeRows.ts` do today. Hooks then call it. No new packages:
   there is no React Testing Library, and installing one needs the owner's yes.
3. **Write the failing test first** (deferred promises, reversed resolution order), then the fix.
4. **Gate:** `node ~/.agents/gates/verify.mjs` from `Frontend/` must print PASS; UI-touching batches also need the
   browser checks in VERIFICATION_PLAN.md.
5. **Rollback** = `git revert <batch commit>`. Each batch is one commit, with no schema or storage migration unless stated.
6. Files stay under 300 lines; `TourPopover.tsx` already exceeds that, so leave it alone.
7. Keep everything in FRONTEND_FINDINGS.md § "Preserve while fixing".

## Track A: frontend (our scope)

| Batch | Fixes | Files (all under `Frontend/src/`) | Depends on | Risk |
|---|---|---|---|---|
| A1 | FE-02, FE-07 | `api/client.ts`, `api/InstancesProvider.tsx`, `api/instancesContext.ts`, `app/chat/ChatPage.tsx` | — | Low |
| A2 | FE-10, FE-12 | `ui/micro/useMicLevel.ts`, `ui/micro/VoicePill.tsx`, `app/voice/useSpeechToText.ts` | — | Medium |
| A3 | FE-01 (incl. create-flow N1) | `api/InstancesProvider.tsx` + new `api/listSequence.ts` (+ test) | A1 | Medium |
| A4a | FE-04 | `api/useLiveStream.ts` (+ extend `liveState.ts`/test) | — | Medium |
| A4b | FE-03, FE-05, FE-06, FE-08 | `api/useLiveStream.ts` (+ new `api/snapshotGate.ts` + test) | A4a | **High**: core live view |
| A5 | FE-09 | `app/report/useProjects.ts` (+ pure pool helper + test) | — | Low |
| A6 | FE-11 | `app/files/localProjects.ts` | — | Low |
| A7 | FE-13 | `app/files/localProjects.ts`, storage keys, `app/auth/AuthProvider.tsx` | **owner decision**, A6 | Medium (user data) |
| A8 | N4, N5 | `server/jwt.ts`, `server/proxy.ts` (+ tests), `app/auth/AuthProvider.tsx` | — | Medium: the Pages Function is a deploy artifact |
| A9 | Sweep of the unchecked files | read-only first; fixes become new batches | — | — |

A1, A2, A5 and A6 touch different files and can run in parallel. A3 waits for A1. A4b waits for A4a. A7 waits for the owner.

### A1: honest errors, no false "deleted"
- `client.ts` `detailOf`: a body starting with `<` → `"The AWDAX server didn't answer (HTTP 524)."`; JSON `detail` unchanged; empty → `HTTP <status>`.
- Provider exposes `listOk` (last list read succeeded). `ChatPage.tsx:85` infers deletion only when `listOk`; otherwise it falls through to the detail state and shows `loadError` or the chat.
- Tests: `detailOf` for 524 HTML, 502 plain text, JSON detail, empty body, and 200 HTML → NOT_CONNECTED (unchanged).
- Browser: Playwright-routed 524 on `/api/instances` with a 200 detail → the chat renders and the sidebar shows the short message.

### A2: microphone and dictation lifecycle
- `useMicLevel`: `startGen` ref; after `await getUserMedia`, if the generation changed or the hook unmounted → stop tracks and close the context, then return.
  Close the context on the catch path. Its own unmount effect calls `stop()` unconditionally. Keep the latest callbacks in refs so the effect doesn't restart each render.
- `VoicePill.tsx:86`: drop the stale mount-only `stop('unmount')`; the hook owns cleanup.
- `useSpeechToText.ts` `onresult`: `if (recognitionRef.current !== recognition) return` first.
- Tests: fake `getUserMedia` resolving after stop, after unmount, two starts resolving in reverse, and denial. Assert track `.stop()` and `context.close()` calls.
- Browser: start dictation → navigate to another chat → no live tracks (`navigator.mediaDevices` stub counts them).

### A3: list ordering
- New pure `listSequence.ts`: `begin()` returns a token `{ req, mut }`; `accept(token)` is true only for the newest request with no mutation since it began; `mutated()` bumps `mut`.
- `refresh` uses it; `upsert`, `remove` and `rename` call `mutated()`. After a rejected stale result, keep the current list (a fresh refresh is already queued by the broadcast).
- Tests: create during an in-flight GET (the new id survives), rename during GET, delete during GET, two GETs resolving in reverse.
- Browser: delay `GET /api/instances` by 3 s, create a chat → its page never shows "no longer exists".

### A4a: one state source for live callbacks
- In the effect, a closure-local `current: LiveState`. Every transition is `current = reduce(current, event)`, then `setTagged({ ...current, forId })`, and callbacks read `current`.
- Put `reduce` in `liveState.ts` and extend its existing tests. Assert the callback payload equals the committed state for open → hello → rows.
- Browser: watched chat, socket opens with 500 rows → no "new rows" toast or notification.

### A4b: snapshot gate
- `snapshotGate.ts`: `begin(filter, runId)` → generation; frames arriving while loading are buffered; `finish(gen, table)` returns `merge(table, buffered)`
  through `mergeRows.ts`, or `null` when stale. A reset or rescore clears the buffer, so removed rows are not revived.
- Hook changes: publish the table without waiting for sources/stats (load those separately). `applyRows` triggers `loadFull()` when `!loaded && !loading`. `finally` checks `!closed`.
- Tests: row arrives mid-snapshot (kept), duplicate ids (one copy), filter toggled mid-request (old result dropped), reset mid-snapshot (not revived), unmount with a queued refresh (no further call).
- Browser: delayed dataset GET while frames stream → the count never drops. First dataset GET fails → the table fills once rows arrive.
- **Highest regression risk.** Reviewer must compare row counts and visible rows on a recorded live session before and after.

### A5: one polling cycle at a time
- `alive` checked inside the worker loop; a `running` flag skips a tick while the last cycle is still in flight; a per-id `changedAt` stamp set by manual `setSnap` drops GETs that started earlier.
- Tests: two slow cycles never exceed 6 concurrent; unmount stops further requests; a pause during a slow GET keeps "paused".

### A6: atomic rename
- `renameLocal`: one readwrite transaction does `get` then `put`, and does nothing if the row is gone; `changed()` fires after `oncomplete`. `db.close()` on `onerror`/`onabort` too.
- Test: fake IndexedDB isn't available in Node, so test the extracted "apply rename to record or null" function and verify the transaction shape in review. Browser: rename and delete in two tabs.

### A7: per-user browser storage (needs the owner's decision first)
Options: (1) **recommended:** namespace IndexedDB and `localStorage` keys by Supabase `user.id`, with a one-time migration that moves today's unscoped data to the first account that signs in; or (2) clear local data on sign-out (simple, but loses a user's uploads). No data is deleted without the owner choosing.

### A8: proxy and auth hardening (owner deploys the Pages Function)
- `jwt.ts`: memoize the in-flight JWKS promise; `AbortSignal.timeout(5000)` on the JWKS fetch. `proxy.ts:79`: a timeout on the origin fetch → the existing `OFFLINE` 503. Skip it for `text/event-stream` and the live stream path, which must stay open.
- `AuthProvider.tsx:46`: add `.catch` that keeps the existing session.
- Tests: extend `server/proxy.test.ts` (timeout → 503 JSON; stream path not timed out; 10 parallel cold calls → 1 JWKS fetch).

### A9: sweep
Read `useCopyToClipboard.ts`, `FuseButton.tsx`, `SmoothScroll.tsx`, `useAutoTour.ts`, `TourHost.tsx`, `SwipeToast.tsx`, `AskPage.tsx`,
`ExportDialog.tsx`, `Layout.tsx` effects and the `liveSocket.ts` CONNECTING watchdog. File anything new into FRONTEND_FINDINGS.md before fixing it.

## Track B: backend (read-only for agents: owner approval or the backend owner)

Listed by urgency. This plan does not change any backend file.

| Batch | What | Why (claim) |
|---|---|---|
| **B1** | Stop trusting `X-User-Id` from arbitrary callers: require a shared proxy secret header, or verify ES256 tokens against Supabase JWKS in Python. Remove the unverified-decode fallback. | C2, C8. Anyone reaching the origin can impersonate any user. |
| **B1** | Scope **every** per-instance route by user (`load_instance_session(id, uid)`), the WebSocket included. DELETE must check ownership **before** `stop_live`. | C1 |
| **B1** | Decide what happens to legacy `user_id='anonymous'` rows (assign them to the owner, or hide them). Never serve that bucket to signed-in users. | C4, C5 |
| B2 | Cherry-pick the useful hunks of `c590915`: WAL in both connection helpers, closing DB handles before PDF/LLM calls, setting running flags before `t.start()`. Resolve its three conflicts **keeping `main`'s user scoping** and `main`'s `NewChat.tsx`. | C7, C12, C13 |
| B3 | Diagnose the 524 with logs before fixing: origin reachability, Flask dev server with `debug=True` (`app.py:739`), the WebSocket `sub.get()` with no timeout (`routes.py:301`), and request latency of `/api/instances` (2N+2 SQLite connections, a DDL run on every call). Run behind a production WSGI server. | C6, C14 |
| B4 | Title and payload lost updates: `save_session` should not write `title` (renames go only through `update_session_title`), and background writers should update their fields, not the whole payload. | C11 |

## Track C: what to do with the five branch-only commits

| Commit | Recommendation |
|---|---|
| `825b086`, `861f1c9`, `92130ba` (tour) | Cherry-pick one at a time onto a `feat/tour-followups` branch after review. UI-verify on 1536×864 and phone width. |
| `c590915` | Frontend hunk (`isUntitled` in `groupByDay.ts`): cherry-pick with A1. `NewChat.tsx` hunk: drop it (`main` already passes the goal). Backend hunks → B2. |
| `233fb40` (ranges, trimmed mean) | **Hold.** Needs owner answers (below). If accepted: label midpoint values in tile footers; add tests for hyphenated non-ranges (phone numbers, "2024-25", model codes); either wire `trimmedMean` as an explicit "robust average" or delete it. |

## Owner decisions needed (blocking the batches named)

1. **A7:** per-user storage with migration (recommended) or clear on sign-out?
2. **Track B:** may an agent change the backend for B1–B4, or does the backend owner take them? (Your standing rule says backend is read-only.)
3. **233fb40:** may price ranges count as their midpoint in totals and averages? Do you want a separate "robust average" (trimmed mean)?
4. **Where we work:** this clone lives at `X:\Hackathons\Codecubicle\awdax-audit`, outside your single `awdax\` folder. Keep it, or move it into `awdax\`?
   Note `awdax\Frontend` (repo AWDAX/Frontend) is now 87 files behind the monorepo's `Frontend/`. Which repo deploys production?
5. **Production:** how is `awdax.synapical.com` built and hosted, and does it call the backend through `/api` (the Pages proxy) or a direct `VITE_API_BASE_URL`?

## Suggested order

A1 → A2 (parallel with A5, A6) → A3 → A4a → A4b → A8 → A9 → tour cherry-picks. B1 goes to the backend owner **today**:
it is the only item that exposes users' data to other people.
