# Frontend findings: races, stalls, lifecycle

Baseline `main` @ `6fc90ba`. Paths are under `Frontend/src/`.
Two independent passes: the first audit, then a separate read-only reviewer that re-checked every step and line.
Line numbers below are the reviewer-corrected ones.

**Confirmed** = the bad interleaving is reachable in source. **Plausible** = it depends on browser, network or scheduler
timing that was not reproduced. Nothing here was reproduced in a browser yet; VERIFICATION_PLAN.md does that.

**Deadlocks: none found.** No lock cycle, no IndexedDB transaction that can't complete, and no awaited promise that can
never settle except FE-05 (bounded at about 100 s in production by Cloudflare) and N5 (plausible).
The Supabase auth callback does not await Supabase calls, so the usual auth-lock deadlock is absent.
The real problems are **races** (stale responses overwriting newer state) and **lifecycle leaks** (work outliving its screen).

## Priority order

| ID | What the user sees | Sev | Verdict | Effort |
|---|---|---|---|---|
| FE-02 | Every chat says "This chat no longer exists" while the list endpoint is failing | High | Confirmed | S |
| FE-10 | Microphone stays on (browser mic indicator lit) after leaving a chat or after the pill shows "off" | High | Confirmed | M |
| FE-01 | Brand-new chat shows "no longer exists"; renamed title or deleted chat briefly reverts | High | Confirmed | M |
| FE-13 | Second Google account on the same browser sees the first account's uploaded files | High (privacy, shared device) | Confirmed | M |
| FE-04 | Spurious "500 new rows" toast and desktop notification for watched chats | Medium | Confirmed mechanism | M |
| FE-03 | A streamed row vanishes from the table and the count drops back | Medium | Confirmed | M |
| FE-05 | Table stays empty while counts climb, after a failed first load | Medium | Partly confirmed | M |
| FE-09 | Paused project flips back to live in the report; requests keep firing after leaving it | Medium | Confirmed | M |
| FE-07 | Gateway HTML shown as error text (dev / direct-origin builds only) | Low | Confirmed, scope narrowed | S |
| FE-06 | Old-filter rows shown under the new "include partial" checkbox for one request | Low | Confirmed | S |
| FE-08 | One redundant round of GETs after leaving a chat | Low | Confirmed | S |
| FE-11 | Deleted uploaded file returns after a near-simultaneous rename | Low | Confirmed, rare | S |
| FE-12 | Dictation loses its auto-stop after a quick restart | Low | Plausible | S |
| N4 | Proxy: parallel JWKS fetches, no timeouts | Low | Plausible | S |
| N5 | Sign-in gate could spin forever on "Checking your sign-in…" | Low | Plausible | S |
| FE-14 | A pending delete silently un-happens: the struck-through row snaps back, or leaving the page cancels it | Medium | Confirmed | S |
| FE-15 | Fuse commit runs the handler from the render that armed it | Low | Latent (no current call site affected) | S |
| FE-16 | Copy button flips back to "idle" early after two quick copies | Low | Confirmed, cosmetic | S |
| N6 | Live view sits on "connecting" if the WebSocket handshake hangs | Low | Plausible | S |

FE-01 to FE-13, N4 and N5 were fixed on `fix/stability-pass` (merged in PR #4). FE-14 to FE-16 and N6 come from the A9 sweep on `main` @ `e824f6c`.

## FE-01: stale list responses overwrite newer state

`api/InstancesProvider.tsx:25`–`:35` has no request ordering. Refreshes come from a 5 s interval, focus and BroadcastChannel (`:38`–`:42`), and they overlap.
1. A list GET starts. 2. The user creates, renames or deletes a chat (`:67`, `:73`, `:82`; `app/chat/NewChat.tsx:68`–`:72`). 3. The old GET lands and `setList` replaces everything.
- **Create:** the new chat's id is missing, so `app/chat/ChatPage.tsx:85` renders "This chat no longer exists." on the chat the user just made (reviewer N1).
- **Rename/delete:** the old title or the deleted row comes back until the next refresh, usually within 5 s. The sending tab also receives its own broadcast, which shrinks the window.
**Fix:** a `mutationSeq` counter bumped by upsert, remove and rename. `refresh` captures it and a request id, and drops the result if either changed.
Consumers to keep working: `app/report/useProjects.ts:55`, `ChatPage.tsx:27`, `NewChat.tsx:70`, `app/workspace/HistoryList.tsx:34`, `app/workspace/HistoryItem.tsx:45`.

## FE-02: a failed list read is treated as "chat deleted"

The initial `list` is `[]` (`InstancesProvider.tsx:20`). A failed read still sets `loading=false` (`:30`–`:33`). `ChatPage.tsx:85` checks absence from the list
**before** the `loadError` branch at `:98`, so during any list outage (524, 401, network) every chat URL says it was deleted, even when its own detail GET worked.
**Fix:** expose `listOk` and infer deletion only from a successful latest list read. A per-instance 404 (`ChatPage.tsx:44`, `api/useLiveStream.ts:146`) already covers real deletion.

## FE-03: an HTTP snapshot drops rows that streamed in while it was loading

Once loaded, frames merge straight into the dataset (`api/useLiveStream.ts:77`). A snapshot then replaces it wholesale (`:126`–`:133`).
Snapshot starts with rows 1–10 → socket adds row 11 → snapshot lands with 1–10 → row 11 disappears until the next `batch_complete`/`resync` (`:201`–`:203`).
**Fix:** while `loading.current` is true, also push frames onto `pending`. `drain` replays them and `api/mergeRows.ts:94`, `:102` dedupes by record id.
Do not resurrect rows a reset or rescoring removed: scope the buffer to the current run and filter.

## FE-04: callbacks read state that React has not computed yet

`publish` (`useLiveStream.ts:50`–`:67`) sets `next` inside a `setState` updater and reads it right after. React runs that updater eagerly only when nothing else is pending.
Interleaving: socket `open` schedules a state update (`:272`), then the `hello` frame arrives before React renders. `publish` emits `rows_total: 0`, and `ChatPage.tsx:60` stores `lastRows = 0`.
The next real payload (say 500 rows) passes `ChatPage.tsx:61` and fires a "500 new rows" toast plus a system notification (`:64`–`:65`).
**Fix:** keep one closure-local `current` in the effect. Each transition does `current = f(current)`, then `setTagged({ ...current, forId })`, and the callback reads `current`. One consumer only (`ChatPage.tsx:54`).

## FE-05: the table can stay empty after a failed first load

- **Confirmed:** if the first snapshot fails while the socket is healthy, `applyRows` (`useLiveStream.ts:77`–`:80`) queues rows forever, because `loaded` is false and nothing retries. Counts climb, the table stays empty.
- **Plausible:** `Promise.all` (`:126`–`:130`) waits for optional sources and stats too, so one hung side request blocks dataset publication. Requests have no deadline (`api/client.ts:44`–`:57`); in production Cloudflare caps them at about 100 s.
**Fix:** (a) in `applyRows`, call `loadFull()` when `!loaded && !loading`; (b) publish the table first, load side data separately.
Deadlines are a separate, later change. **Never auto-retry** a timed-out create, delete or message POST: its server outcome is unknown.

## FE-06: the "include partial" result can lag the checkbox

The request captures `includePartial` (`useLiveStream.ts:127`), and the checkbox flips first (`:259`–`:262`). For one request the table shows old-filter rows under the new label.
**Fix:** tag each request with a filter generation and drop mismatched results. Capturing the value alone would make the checkbox flicker.

## FE-07: non-JSON error bodies are shown as text

`api/client.ts:16`–`:23` returns the raw body as the message; `HistoryList.tsx:34`, `:41` and `ChatPage.tsx:102` render it. React escapes it, so this is **not** XSS.
**Scope:** the production proxy already turns non-JSON upstream 5xx into a short JSON message (`server/proxy.ts:91`).
Raw HTML reaches the UI only in local dev or in a build whose `VITE_API_BASE_URL` points straight at a Cloudflare-fronted backend.
**Fix:** in `detailOf`, a body that starts with `<` becomes a short "server didn't answer (HTTP 524)" message; keep the status. Keep JSON `detail` and the static-host detection at `:60`–`:65`.

## FE-08: queued snapshot runs once more after cleanup

`finally` (`useLiveStream.ts:150`–`:155`) re-launches a queued `loadFull` after unmount or a terminal 404. Results are dropped by the `closed` checks (`:131`, `:145`).
No reconnect and no late callback happen (the first audit overstated this). Impact: one redundant round of GETs.
**Fix:** `if (again.current && !closed)`.

## FE-09: project polling overlaps, regresses status, and outlives the screen

`app/report/useProjects.ts:43`–`:48`, `:62`–`:75`. Every 15 s tick starts a new six-worker pool, even if the last one is still running.
- An older GET can overwrite a manual pause/resume `setSnap` (`app/report/ProjectsReport.tsx:64`) until the next cycle.
- Overlapping pools exceed six concurrent requests.
- The `while` loop (`:46`) keeps requesting the remaining ids after unmount. `alive` only guards `setSnaps`, so 50 projects means up to about 44 wasted requests per abandoned cycle.
**Fix:** check `alive` inside the loop, a `running` flag to skip overlapping ticks, and a per-id "changed at" stamp that drops older GETs.

## FE-10: microphone outlives the pill (privacy)

1. `ui/micro/VoicePill.tsx:86` registers a mount-only cleanup that closes over `listening=false`, so `stop('unmount')` returns early (`:46`). Leaving a chat while dictating leaves the mic tracks live, the browser's mic indicator on and an animation loop running. Layout remounts on every route change, so this is common.
2. `ui/micro/useMicLevel.ts:35`–`:37` awaits `getUserMedia` and then assigns the stream with no "still wanted?" check. If recognition ends during the permission prompt, `VoicePill.tsx:80`–`:82` fires `stop('ended')` while the stream is still unassigned. The late grant then starts the mic **with the pill showing off**, with no user action needed.
3. When permission is denied, the `AudioContext` is never closed.
**Fix (in `useMicLevel`):** a start-generation ref (after the await: if stale or unmounted, stop the tracks and close the context), an unmount effect that always calls `stop()`, and closing the context on the error path.

## FE-11: rename can resurrect a deleted uploaded file

`app/files/localProjects.ts:71`–`:76` reads in one transaction and writes in another. A delete that commits between them is undone.
It needs two tabs or near-simultaneous clicks, so this is rare. Also, `run()` closes the DB only on `oncomplete` (`:38`–`:43`) and leaks a connection on error or abort.
**Fix:** get and put in one readwrite transaction, doing nothing if the row is gone. Close on error and abort too.

## FE-12: stale recognizer result cancels the new session's silence timer

`app/voice/useSpeechToText.ts:106`–`:118`: `onresult` lacks the identity check that `onerror`/`onend` have. A result from an aborted recognizer re-arms the **shared** `timerRef` (`:97`–`:103`).
The new session then loses its auto-stop until it hears speech. Plausible: the spec says no results after `abort()`, but browsers vary.
**Fix:** one line at the top of `onresult`: `if (recognitionRef.current !== recognition) return`.

## FE-13: browser storage is not scoped to the signed-in user

Uploaded-file projects live in IndexedDB `awdax` / `projects` (`app/files/localProjects.ts:20`–`:27`) and show in the sidebar (`HistoryList.tsx`, `useLocalProjects.ts`).
Per-chat answers, dashboards, graphs, visits, alerts and legacy titles live in unscoped `localStorage` keys.
Sign-out (`app/auth/AuthProvider.tsx:74`–`:75`) clears none of it. On a shared browser the next Google account sees the previous account's uploaded tables and their saved Q&A.
**Fix (product choice, see REMEDIATION_PLAN.md open questions):** key storage by Supabase `user.id` (a new DB name per user, with a one-time migration of the current data to the first account that signs in), or clear on sign-out. Never delete data silently without the owner's choice.

## N4: proxy JWKS fetch has no timeout and no shared in-flight promise

`server/jwt.ts:52`–`:54`: parallel cold requests each fetch JWKS, and `fetchJwks` (`:31`) has no deadline. The origin fetch (`server/proxy.ts:79`) has no timeout either.
**Fix:** memoize the in-flight promise; `AbortSignal.timeout` on both fetches. The proxy reads the body only once (`:82`), so there is no double read.

## N5: sign-in check has no rejection path

`app/auth/AuthProvider.tsx:46`: `getUser().then(...)` without `.catch`. If it ever rejects, `confirmed` never sets and the gate spins.
supabase-js normally resolves with `{ error }`, hence plausible. **Fix:** a `.catch` that keeps the existing session (same policy as `:53`–`:55`).

## FE-14: an undo-window delete is cancelled when its component unmounts

Both fuses commit from an animation's `onfinish` and call `anim.cancel()` in effect cleanup: `ui/micro/FuseButton.tsx:73`–`:78` and
`app/workspace/HistoryItem.tsx:60`–`:65`. Unmounting during the window therefore drops the delete with no message. Reachable paths:
- **Sidebar regroup.** `HistoryList.tsx:43` keys sections by day label, so a chat that moves group remounts its `HistoryItem` and `phase` resets to `idle`.
  The list refreshes every 5 s (`api/InstancesProvider.tsx:12`, `:47`) and on window focus. A chat from yesterday with a running track gets a new
  `updated_at`, moves to "Today" and loses its pending delete within the 4 s window. The row snaps back un-struck. The same happens at midnight
  and when the sidebar search filters the row out.
- **Leaving the page.** "Delete chat" (`app/chat/ChatPage.tsx:125`) and "Delete" (`app/chat/FilePage.tsx:62`) live inside `<main key={pathname}>`
  (`Layout.tsx:114`). Opening another chat within the 5 s window unmounts the button, and the chat is never deleted.
- **Project report.** A `ProjectRow` filtered or paged out of `ProjectsReport.tsx:133` cancels its delete the same way.

**Fix (needs the owner's choice of behaviour):** (a) **recommended:** an armed fuse that unmounts commits immediately, since pressing Delete was the
intent and Undo/Escape are the only explicit cancels. That is one ref in each cleanup. Alternatively, (b) lift pending deletes into `InstancesProvider`
(`pending: Set<id>` plus one timer per id), so a remounted row shows its struck-through state again. (b) is more code but keeps the visible undo.

## FE-15: FuseButton reads `onCommit` from the render that armed it

`ui/micro/FuseButton.tsx:66`–`:80` disables `exhaustive-deps`, so `onfinish` calls the `onCommit` captured when `phase` became `armed`.
`HistoryItem.tsx:51`–`:56` already avoids this with a latest-value ref (`delRef`). No current call site is wrong: each closes over values that
stay fixed for the mount, because pages remount per pathname. A future call site whose handler depends on changing state would commit stale data.
**Fix:** the same latest-ref pattern as `delRef`, applied to `onCommit` (and `onUndo`). Do it together with FE-14, since it touches the same effect.

## FE-16: overlapping copies leak a reset timer

`ui/micro/useCopyToClipboard.ts:19`–`:29` clears the timer at the start of `copy`, but sets it in `finally` after the `await`. Two copies inside one
clipboard write both pass the clear, both set a timer, and the first one's id is overwritten, so the label resets early. The timer is not cleared on
unmount either (harmless in React 18+). **Fix:** clear inside `finally` before setting, plus an unmount cleanup. Cosmetic: do it only when touching the file.

## N6: no watchdog for a WebSocket stuck in CONNECTING

`api/liveSocket.ts:20`–`:57` counts failures only on `close`. A handshake that a proxy holds open never fires `open` or `close`, so the page waits
for the browser's own timeout before the SSE fallback (`:48`–`:51`). `onVisibility` (`:60`–`:66`) doesn't help because `socket` is non-null.
Plausible: it depends on the proxy. **Fix:** a 10 s timer started in `connect()`, cleared on `open`. If it fires while
`readyState === CONNECTING`, call `socket.close()`, and the existing `close` path counts the failure.

## Checked and clean

- Auth: the `onAuthStateChange` callback only sets state and the stream cookie. No Supabase call is awaited inside it, so it has no lock cycle.
- Storage events: `chatTitles.ts`, `alerts.ts` and `useSignedInHint.ts` never write from their handlers, so they cannot ping-pong.
- No infinite render loops. The render-phase setState in `GraphsPanel.tsx` and `useDashboard.ts:53` converges.
- BroadcastChannel: a refresh never re-notifies; the subscriber closes (`api/instancesSync.ts:22`). The posting channel (`:8`) is a throwaway object: hygiene only.
- `Layout.tsx` keys content by pathname, which already prevents cross-chat retained state. **Keep it.**

- A9 sweep (`main` @ `e824f6c`), no race found:
  - `SmoothScroll.tsx` and `useAutoTour.ts` clean up their timers.
  - `TourHost.tsx`: every rAF loop and the Lenis `onComplete` check `isCancelled`, and every listener is removed.
  - `AskPage.tsx` has an `alive` guard and only shows a table whose key matches the selected project.
  - `ExportDialog.tsx`: a late `setBusy` after close is harmless.
  - `Layout.tsx`: storage write and Escape listener are fine.
  - `SwipeToast.tsx` uses the same arm-time closure as FE-15, but `onDismiss(id)` comes from the toast host and its `id` is fixed per toast.

## Preserve while fixing

Row-id dedupe (`mergeRows.ts`), pathname remounting, per-instance tagged stream state, typed API adapters,
exact decimal arithmetic, React-escaped error text, the proxy's JSON error rewrite, and the uploaded-file fallback.
