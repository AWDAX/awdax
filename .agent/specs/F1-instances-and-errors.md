# Spec F1: honest errors, list ordering, chat creation (FE-01, FE-02, FE-07, N1 + orphan chats)

Read `.agent/specs/FE-common.md` first. Files you own (only these):
`Frontend/src/api/client.ts`, new `Frontend/src/api/errorText.ts` + `errorText.test.ts`,
`Frontend/src/api/InstancesProvider.tsx`, `Frontend/src/api/instancesContext.ts`, new `Frontend/src/api/listSequence.ts` + `listSequence.test.ts`,
`Frontend/src/app/chat/ChatPage.tsx` (only the deletion-inference condition), `Frontend/src/app/chat/NewChat.tsx` (only `submit`),
`Frontend/src/app/workspace/groupByDay.ts` (only `isUntitled`).

## 1. Error text (FE-07)
Move `detailOf` from `client.ts` into pure `errorText.ts` as `export function detailOf(text: string, status: number): string` and import it back in `client.ts`.
New rule: if the trimmed body starts with `<` (an HTML error page), return `` `The AWDAX server didn’t answer (HTTP ${status}). Try again in a minute.` ``.
JSON `{detail: string}` → that string (unchanged). Plain non-empty text → the text, cut to 200 chars. Empty → `HTTP ${status}`. Everything else in `request()` stays as is.
Tests: 524 Cloudflare HTML; 502 plain text; JSON detail; empty body; long plain text truncated.

## 2. List ordering (FE-01, N1)
Pure `listSequence.ts`:
```ts
export type ListToken = { req: number; mut: number }
export function createListSequence(): { begin(): ListToken; accept(t: ListToken): boolean; mutated(): void }
```
`begin` increments and captures the request counter and the current mutation counter. `accept(t)` is true only if `t.req` is the newest request started **and** no mutation happened since `t` began.
In `InstancesProvider`: keep one sequence in a ref. `refresh` takes a token before awaiting; after the await, if `!accept(token)` drop the result (do not `setList`, do not clear `error`) but still end `loading`.
`upsert`, `remove`, `rename` (and the local-title migration's update) call `mutated()` **before** changing the list. After any dropped result, the broadcast/interval refresh brings the list current; do not add new timers.
Tests: create during an in-flight read (stale read rejected); rename during read; delete during read; two reads resolving in reverse (older rejected); a read started after a mutation is accepted.

## 3. No false "chat deleted" (FE-02)
Add `listOk: boolean` to the `Instances` type and provider value: true after the latest **accepted** list read succeeded, false after a failed read (initially false).
In `ChatPage.tsx` change only the deletion inference: `(!listLoading && listOk && !!id && !list.some(...))`. Real deletions still show via `missing` (detail 404) and `live.missing`.
Destructure `listOk` from `useInstances()` there.

## 4. Chat creation never leaves an orphan "Untitled chat" (the owner's "pending" symptom)
In `NewChat.tsx` `submit` (web branch only; leave the file-upload branch alone):
- `createInstance(goal.trim().slice(0, 80))` (title = the prompt, like the backend's own rule).
- If `startTracking` throws:
  - `ApiError` with status 409 → the run exists: `upsert(created)`, `notifyInstancesChanged('create')`, navigate to the chat.
  - `ApiError` with status 400, 401, 403, 404, 422 or 500 (a definite answer from the server) → best-effort `awdax.deleteInstance(created.id).catch(() => {})`, then the existing error toast.
  - anything else (status 0, 502, 503, 504, 524, non-ApiError) → outcome unknown: do NOT delete and do NOT retry; `upsert(created)`, `notifyInstancesChanged('create')`,
    navigate to the chat, and toast `{ title: 'The server didn’t confirm the start', description: 'This chat will update when the server answers.', tone: 'error' }`.
- Keep `setBusy(false)` behaviour on the error paths that stay on the page.

## 5. Untitled detection
`groupByDay.ts` `isUntitled`: treat `''`, `New track`, `Untitled chat`, `New session` and `Session 1` (trimmed) as untitled (the backend's defaults).

## Done
Tests above pass; eslint and tsc clean for your files.
