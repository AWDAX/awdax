# Verification plan

How each batch in REMEDIATION_PLAN.md is proven before it counts as done. A check that could not run is reported as **UNVERIFIED**, never as a pass.

## Baseline (recorded)

| Check | Result | Evidence |
|---|---|---|
| `npm ci` (lockfile only, owner-approved) | exit 0; 2 moderate advisories, not force-fixed | `.agent/runs/_adhoc/001-npm-ci.json` |
| `verify.mjs` on `main` @ `6fc90ba`: lint, types, build, tests | **PASS** (all four) | `.agent/evidence/baseline-verify.json` |
| Backend tests | **not run**: backend is outside agent scope | — |
| Browser reproduction of any FE finding | **not run yet**: first step of each batch | — |

The baseline proves the code builds and the existing tests pass. It does **not** prove the races are absent: no current test covers them.

## Per-batch evidence (all required)

1. **Failing test first:** the new Node test reproduces the interleaving on the unfixed code (deferred promises resolved in a chosen order). Record the failing run.
2. **Code gate:** from `Frontend/`, `node ~/.agents/gates/run.mjs -- node ~/.agents/gates/verify.mjs --json` → PASS, saved under `.agent/evidence/`.
3. **Browser check** for every batch that changes what renders (A1–A5, A7, A8). Record the result per the `ui-verification` skill:
   routes, viewports, console errors (must be 0), failed requests, assertions, screenshots.
4. **Review:** an Opus `reviewer` pass with no open blocking findings, made against the final diff (not an earlier one).

## Browser harness (no backend needed)

- Start `npm run dev:agent` (port 5174; opens `/app` without Google sign-in).
- Drive it with the **Playwright MCP**, not the hidden Browser pane (the hidden pane throttles timers and animations; see the owner's earlier finding).
- Fake the API with `page.route('**/api/**', …)`: delay, reorder, fail, or answer with Cloudflare-style HTML. WebSocket frames use `page.routeWebSocket` where the MCP exposes it;
  otherwise force the SSE/polling fallback and mark the socket-specific step **UNVERIFIED**.
- Stub `navigator.mediaDevices.getUserMedia` in an init script that counts live tracks, and stub `AudioContext` to count `close()` calls.
- Viewports: 1536×864 (the owner's laptop) and 375×812.

## Scenario matrix

| Batch | Scenario | Pass condition |
|---|---|---|
| A1 | `GET /api/instances` → 524 HTML; `GET /api/instances/:id` → 200 | Chat renders. Sidebar shows one short sentence, no `<!DOCTYPE`. No "no longer exists". |
| A1 | Detail → real 404 JSON | "This chat no longer exists." still shows. |
| A1 | 200 HTML (static host) | The existing NOT_CONNECTED message, unchanged. |
| A2 | Start dictation, then navigate to another chat | Live track count returns to 0; `AudioContext.close` called once. |
| A2 | `getUserMedia` resolves 2 s late, after recognition ended | No live tracks afterwards; the pill shows off. |
| A2 | Permission denied | Context closed; no animation loop running. |
| A3 | List GET delayed 3 s, then create a chat | The new chat never shows "no longer exists"; it appears in the sidebar. |
| A3 | List GET delayed, then rename | The title never reverts. |
| A3 | Two list GETs resolve in reverse order | The newest wins. |
| A4a | Watched chat, socket opens, hello with 500 rows | No "new rows" toast; no `Notification` constructed (stubbed counter). |
| A4b | Dataset GET delayed 3 s while 5 row frames arrive | Visible row count never decreases; final count = snapshot ∪ frames. |
| A4b | First dataset GET fails, socket healthy | Table fills after the next frame (or retry); no permanent empty table. |
| A4b | Toggle "include partial" twice quickly with reversed delays | Table matches the final checkbox state. |
| A4b | Leave the chat with a refresh queued | No further `/dataset` request after unmount. |
| A5 | Every `getLive` takes 20 s, report open for 40 s | Never more than 6 in flight. Leaving the report stops new requests. |
| A5 | Pause a project while its GET is slow | Status stays "paused". |
| A6 | Rename and delete the same uploaded file from two tabs | The file stays deleted. |
| A7 | Account A uploads a file, signs out; account B signs in (stubbed auth) | B sees none of A's files. A sees them again after signing back in (or as the owner decided). |
| A8 | 10 parallel cold `/api` calls | One JWKS fetch (unit test). Origin hang → 503 JSON within the timeout; the live stream path is not cut. |

## Regression smoke (every batch)

`/`, `/login`, `/privacy`, `/app` (new chat), `/app/f/:id` with a 74-row fixture, Projects report, Graphs, Export dialog, tour start.
Pass: renders, 0 console errors, no failed requests other than the ones faked on purpose, no horizontal scroll at 375 px.

## Done means

Every class required by the gate is PASS against the code as it stands, the reviewer's approval matches the current diff,
and the batch's scenarios above pass. Anything not run is listed as UNVERIFIED in the report.
