# F6: an undo-window action still happens when its control unmounts (FE-14, FE-15)

Branch `fix/fe-14-15-fuse-unmount`, cut from `main`. Findings: `docs/audit/FRONTEND_FINDINGS.md` § FE-14 and § FE-15.
Owner decision (2 October 2026), option (a): once armed, the action goes through even if its button disappears (the page was left,
the sidebar row moved to another day group, the row was filtered out). Only Undo or Escape cancels.

## Files you may edit

- new `Frontend/src/ui/micro/fuseLatch.ts` and `Frontend/src/ui/micro/fuseLatch.test.ts`
- `Frontend/src/ui/micro/FuseButton.tsx`
- `Frontend/src/app/workspace/HistoryItem.tsx`
- `Frontend/src/app/chat/ChatPage.tsx` (only the Delete chat `onCommit`, plus imports)
- `Frontend/src/app/chat/FilePage.tsx` (only the Delete `onCommit`, plus imports)

## 1. The pure rule: `fuseLatch.ts`

```ts
/**
 * The commit rule behind an undo window (FuseButton, a chat row's Delete): once armed, the action runs exactly once, when the
 * fuse ends or when the control unmounts first, unless Undo came first. Pure, so it is tested without React.
 */
export type FuseLatch = { arm: () => void; undo: () => void; finish: () => void; unmount: () => void }

export function createFuseLatch(commit: () => void): FuseLatch
```

Behaviour: `arm()` makes it pending; `undo()` clears pending; `finish()` and `unmount()` each run `commit` once if pending and
clear pending. Nothing runs if it was never armed. Re-arming after an undo works.

Tests in `fuseLatch.test.ts`, written first:
- arm → finish commits once; a later unmount does not commit again
- arm → unmount commits once; a later finish does not commit again
- arm → undo → finish and unmount: no commit
- never armed → unmount: no commit (mounting and unmounting an idle button, as React StrictMode does, must never commit)
- arm → undo → arm → finish: commits once

## 2. `FuseButton.tsx`

- FE-15: keep the latest `onCommit` in a ref, updated in an effect with no dependency array. That's the same pattern as `delRef` in `HistoryItem.tsx`, which you can copy:
  `const commitRef = useRef(onCommit)` + `useEffect(() => { commitRef.current = onCommit })`.
- One latch per mounted button: `const [latch] = useState(() => createFuseLatch(() => commitRef.current?.()))`.
- `arm()`: keep the guard and `setPhase('armed')`. `commitOn === 'press'` still calls `onCommit?.()` at once and does not
  arm the latch; otherwise `latch.arm()`.
- `undo()`: call `latch.undo()` before cancelling the animation; the rest stays the same.
- The fuse effect: `anim.onfinish = () => { latch.finish(); setPhase('settled') }`. The effect no longer reads `commitOn` or
  `onCommit`, so make its dependency list exhaustive (`[phase, undoWindow, latch]`) and delete the `eslint-disable` line above it.
- Add, with a one-line comment saying why: `useEffect(() => () => latch.unmount(), [latch])`.
- No change to props, markup or classes.

## 3. `HistoryItem.tsx`

- `del()`: replace `if (active) navigate('/app', { replace: true })` with a check of the location at the moment it runs,
  because the delete can now run after the user opened another page:
  `if (matchPath(path, window.location.pathname)) navigate('/app', { replace: true })` (import `matchPath` from `react-router`).
  `active` stays: it still styles the row.
- Update the comment above `delRef` to say it is read when the fuse ends or the row unmounts. Keep `delRef`.
- `const [latch] = useState(() => createFuseLatch(() => void delRef.current()))`.
- The menu's Delete item: call `latch.arm()` next to `setPhase('deleting')`.
- The Undo button's `onClick` and its Escape `onKeyDown`: call `latch.undo()` before `setPhase('idle')`.
- The fuse effect: `anim.onfinish = () => latch.finish()`; add `latch` to its dependency list.
- Add `useEffect(() => () => latch.unmount(), [latch])` with a one-line comment (a row that moves to another day group or is
  filtered out remounts; its pending delete must still happen).

## 4. `ChatPage.tsx` and `FilePage.tsx`

The Delete `onCommit` navigates to `/app` before deleting. When the commit runs because the page unmounted (the user opened another
chat), that navigate would pull them back. Leave only if the user is still on this page:

- `const { pathname } = useLocation()` in the component (import `useLocation`, `matchPath` from `react-router`).
- In the Delete `onCommit`: `if (matchPath(pathname, window.location.pathname)) navigate('/app', { replace: true })`, then the
  existing delete line unchanged. A short comment: the fuse can commit after the page was left.
- Do not touch the Pause tracking FuseButton or anything else in these files.

## Must stay true

- Undo and Escape cancel; nothing commits twice; an idle button never commits.
- When the fuse ends on the page, behaviour is exactly as today: ChatPage and FilePage go to `/app` and delete, and the sidebar row deletes
  (and leaves the chat's page if it is open).
- No change to `ProjectRow.tsx`, `Dashboard.tsx` or `MicroGallery.tsx`: their `onCommit` handlers need nothing.
