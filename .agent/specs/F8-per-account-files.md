# F8: uploaded files belong to the account that uploaded them (FE-13 / A7)

Branch `fix/fe-13-per-account-files`, cut from `main`. Finding: `docs/audit/FRONTEND_FINDINGS.md` § FE-13.
Owner decision (2 October 2026): **separate per account. Nothing is deleted. Files already in the browser go to the first account
that signs in after the update.**

## What actually leaks, and what doesn't

Only the IndexedDB database `awdax` (store `projects`, `app/files/localProjects.ts`) is listed across accounts: the sidebar,
the projects report and Ask database all enumerate it. Every other per-chat key (`awdax.answers.*`, `awdax.dashboard.v2.*`,
`awdax.graphs.v2.*`, `awdax.visits.*`, `awdax.alerts`, `awdax.chat.titles`) is read by chat id only. Nothing enumerates
localStorage, web chats are scoped by the backend, and file chats become unreachable once the database is per account.
So this batch scopes the database and nothing else. Device preferences (sidebar, tours, signed-in hint) stay shared on purpose.

## Files you may edit

- `Frontend/src/app/files/localProjects.ts`
- `Frontend/src/app/files/localProjects.test.ts`
- `Frontend/src/app/auth/AuthProvider.tsx`
- `Frontend/src/app/auth/RequireAuth.tsx`

## 1. `localProjects.ts`

Add, near `const DB = 'awdax'` (keep that name: it is the shared database from before):

```ts
// Before files were per account, every account on this browser shared the 'awdax' database. The first account to sign in
// after that change keeps it as is (nothing is copied or deleted); every other account gets a database of its own.
const OWNER_KEY = 'awdax.files.owner'

/** The database for this account's files. Pure apart from `store`, so it is tested without a browser. */
export function filesDbName(account: string, store: Pick<Storage, 'getItem' | 'setItem'>): string
```

Rules for `filesDbName`:
- if `store.getItem(OWNER_KEY)` is `null`, `store.setItem(OWNER_KEY, account)` and return `DB`;
- if it equals `account`, return `DB`;
- otherwise return `` `${DB}.${account}` ``;
- if `getItem` or `setItem` throws (storage blocked), return `` `${DB}.${account}` ``: never hand the shared database to an
  account we couldn't record.

Then a module-level owner:

```ts
let owner: string | null = null

/** Called by the auth layer once an account is confirmed. Lists re-read when it changes. */
export function setFilesOwner(account: string | null)
```
It does nothing if `account === owner`; otherwise it sets `owner` and calls `changed()`. Keep declaration order valid (`changed`
must be defined before `setFilesOwner` runs).

`open()`: if `owner` is `null`, return `Promise.reject(new Error('Sign in to use uploaded files'))`. Otherwise
`indexedDB.open(filesDbName(owner, localStorage), 1)`. Everything else in `open()` and in the rest of the file stays as is:
`run`, `renameLocal` and `deleteLocal` already go through `open()`. Callers already handle a rejected promise
(`useLocalProjects` catches it and shows an empty list).

## 2. Tests in `localProjects.test.ts`, written first

Keep the existing `renamed` tests. Add, with a small Map-backed fake store:
- `the first account on a browser keeps the shared files database`: empty store, `filesDbName('a', s)` → `'awdax'`, and the
  store now records `'a'`.
- `another account gets a database of its own`: after the above, `filesDbName('b', s)` → `'awdax.b'`.
- `the first account keeps it on later sign-ins`: then `filesDbName('a', s)` → `'awdax'`.
- `blocked storage never hands out the shared database`: a store whose methods throw → `filesDbName('a', s)` → `'awdax.a'`.

## 3. `AuthProvider.tsx`

In the confirmation effect, call `setFilesOwner(userId)` immediately before **each** `setConfirmed(userId)` (the confirmed or
unreachable branch, and the `.catch`). `RequireAuth` renders the app only after `confirmed` matches, so the owner is always set
before any screen lists files. Do not clear it on sign-out: the app is unmounted then, and the next confirmed account replaces it.
Don't call it from inside the `onAuthStateChange` callback. Add one short comment at the first call site.

## 4. `RequireAuth.tsx`

Agent preview (`npm run dev:agent`) has no account. Next to the existing agent bypass, at module level:
```ts
if (import.meta.env.DEV && import.meta.env.MODE === 'agent') setFilesOwner('agent')
```
with a one-line comment. Production builds drop it (`DEV` is false), as they drop the bypass below it.

## Must stay true

- No data is deleted, moved or copied. The existing `awdax` database is never opened for an account other than its recorded owner.
- Uploading, renaming, deleting and listing files behave exactly as today for a signed-in account.
- `localProjects.ts` stays importable in Node (no `import.meta.env`, no Supabase import), because its test imports it.
