# F5: live socket watchdog (N6) and copy reset timer (FE-16)

Branch `fix/fe-16-n6-socket-copy`, cut from `main`. Findings: `docs/audit/FRONTEND_FINDINGS.md` § FE-16 and § N6.
Owner decision (2 October 2026): do both.

## Files you may edit

- `Frontend/src/api/liveSocket.ts`
- `Frontend/src/api/liveSocket.test.ts`
- `Frontend/src/ui/micro/useCopyToClipboard.ts`

## N6: a WebSocket stuck in CONNECTING

Today `openLiveSocket` counts a failure only on `close`. A handshake that a proxy holds open never fires `open` or `close`,
so the page waits for the browser's own timeout before the SSE fallback. `onVisibility` can't help because `socket` is non-null.

Change in `liveSocket.ts`:

1. Module constant `const CONNECT_TIMEOUT_MS = 10_000` with a one-line comment saying why it exists.
2. Closure variable `let watchdog = 0` next to `let timer = 0`.
3. In `connect()`, right after the `try/catch` that creates the socket: `const current = socket` and
   ```ts
   watchdog = window.setTimeout(() => {
     if (current.readyState === WebSocket.CONNECTING) current.close()
   }, CONNECT_TIMEOUT_MS)
   ```
   Close `current`, never the shared `socket` variable: a newer socket may exist by the time the timer fires.
   (`socket` is typed `WebSocket | null`; narrow it so `current` is `WebSocket`.)
4. `window.clearTimeout(watchdog)` as the first statement of the `open` listener and of the `close` listener.
5. In the returned cleanup function, `window.clearTimeout(watchdog)` next to `window.clearTimeout(timer)`.

Nothing else changes. The existing `close` path already counts the failure, backs off, and falls back to events after two.

Must stay true:
- The existing test in `liveSocket.test.ts` passes unchanged (do not edit it).
- A socket that opened is never closed by the watchdog.
- After `stop()`, no timer is pending.

Tests to add to `liveSocket.test.ts`, written first (the first one must fail on today's code):

- `a handshake that never opens is closed after 10 s and counts toward the fallback`
  Fake socket class with `static CONNECTING = 0`, an instance `readyState = 0`, `close()` that sets `readyState = 3`
  and emits `close`, and a `closed` counter. Fake `window` with a real timer table: `setTimeout(fn, ms)` stores
  `{ fn, ms }` under an incrementing id and returns it; `clearTimeout(id)` deletes it. Steps: open the socket; run the pending
  10 000 ms timer, so socket 0 is closed once and `onConnection('reconnecting')` is called; run the pending reconnect timer, so socket 1 exists;
  run its 10 000 ms timer, so `onFallback` is called exactly once and no timer is left pending.
- `an opened socket is not closed by the watchdog`: emit `open` on socket 0, then no 10 000 ms timer is pending and socket 0
  was never closed.
- `stop() clears every timer`: call `stop()` before `open`, then no timer is pending and socket 0 was closed exactly once.

Restore every global you replace in `finally`, as the existing test does. Keep the fakes small, local to the file, and typed the same
way the existing test types them.

## FE-16: the copy button's reset timer

`useCopyToClipboard.ts` clears `resetTimeout` at the top of `copy`, before `await navigator.clipboard.writeText`, but sets it in
`finally`, after the await. Two copies that overlap one write both pass the clear and both set a timer. The first timer's id is
overwritten, so the label flips back to idle early. Nothing clears the timer on unmount either.

Change:

1. In `finally`, clear before setting: `if (resetTimeout.current) clearTimeout(resetTimeout.current)` on the line above
   `resetTimeout.current = setTimeout(...)`. Keep the existing clear at the top of `copy`: it stops a pending reset from flipping
   'done' back to 'idle' while a new write is in flight.
2. An unmount cleanup: `useEffect(() => () => { if (resetTimeout.current) clearTimeout(resetTimeout.current) }, [])`,
   importing `useEffect`.

No API change, no new test file: the repo has no React test renderer and no new packages are allowed. The lead verifies this in the browser.
