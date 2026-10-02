# Spec F2: live stream state and snapshot gate (FE-03, FE-04, FE-05, FE-06, FE-08)

Read `.agent/specs/FE-common.md` first. Files you own (only these):
`Frontend/src/api/useLiveStream.ts`, `Frontend/src/api/liveState.ts` + `liveState.test.ts`, new `Frontend/src/api/snapshotGate.ts` + `snapshotGate.test.ts`.
Do NOT edit `ChatPage.tsx` (its callback stays the same; it must simply receive correct payloads). Highest-risk area of the app: keep behaviour identical except the fixes.

Read the whole current `useLiveStream.ts` (285 lines) and `mergeRows.ts` before changing anything.

## 1. One state source (FE-04)
Today `publish` assigns `next` inside a `setState` updater and reads it right after; React may defer the updater, so `onPayload` can get `EMPTY_LIVE` (rows_total 0),
which makes `ChatPage` fire a false "N new rows" toast/notification later.
Fix: inside the effect keep `let current: LiveState = EMPTY_LIVE` (closure-local, per instance id). Every state change in the effect goes through one helper:
`const update = (fn: (s: LiveState) => LiveState) => { current = fn(current); setTagged({ ...current, forId: id }) }`.
Replace every `setState(...)` call in the effect with `update(...)`. `publish` computes `next` with the existing merge rules (move that pure merge into `liveState.ts` as
`export function applyPatch(s: LiveState, patch: Partial<LiveState>): LiveState`), calls `update(() => next)`, then calls handlers with `next`.
Tests in `liveState.test.ts` for `applyPatch`: sources merged via `mergeSources`, status shallow-merged, `connected` defaults to true, other fields replaced.

## 2. Snapshot gate (FE-03, FE-06)
Pure `snapshotGate.ts`:
```ts
export function createSnapshotGate(): {
  begin(filterKey: string): number            // returns a generation; marks "loading"
  isLoading(): boolean
  buffer(frame: StreamedRows): void          // frames that arrive while loading
  finish(gen: number, filterKey: string, table: DatasetTable): DatasetTable | null  // null if stale (newer begin, or filter changed); else table with buffered frames replayed via mergeStreamedRows, buffer cleared
  reset(): void                              // drop buffer + invalidate in-flight generation (used on a run reset / 404 / unmount)
}
```
Use `mergeStreamedRows` from `mergeRows.ts` for replay. `filterKey` is `includePartial ? 'partial' : 'accepted'`.
In the hook: `loadFull` calls `begin(key)` and passes the generation through; a result whose `finish` returns null is discarded (no publish).
`applyRows`: if `!loaded` OR `gate.isLoading()` → `buffer(frame)` AND (when loaded and `canMerge`) still merge into the current dataset for display, as today.
Keep the existing `pending`/`drain` behaviour only if `snapshotGate` fully replaces it; do not leave two buffers.
Tests: frame during snapshot is kept; duplicate record ids appear once; filter changed mid-request → stale result returns null; two overlapping begins → only the newest finishes;
`reset()` mid-load → that result is null and buffer is empty.

## 3. Initial failure and side data (FE-05)
- `loadFull` publishes the dataset after `getDataset` alone; then loads sources/stats via the existing `loadSide()` (don't await it before publishing).
- In `applyRows`, when `!loaded && !gate.isLoading()`, trigger `void loadFull()` (so a failed first snapshot recovers when rows stream in).
- Do not add request deadlines or retries for POST calls.

## 4. Lifecycle (FE-08)
- `finally` in `loadFull`: re-run only `if (again.current && !closed)`; when closed, clear `again`.
- On 404 and on cleanup call `gate.reset()`.

## Done
Tests pass; eslint/tsc clean for your files. In your report, list every place behaviour could differ for a user (there should be none beyond the fixes).
