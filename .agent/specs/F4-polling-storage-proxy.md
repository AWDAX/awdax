# Spec F4: project polling, uploaded-file rename, proxy JWKS + shared secret (FE-09, FE-11, N4, BK5 proxy half)

Read `.agent/specs/FE-common.md` first. Files you own (only these):
`Frontend/src/app/report/useProjects.ts`, new `Frontend/src/app/report/pollPool.ts` + `pollPool.test.ts`,
`Frontend/src/app/files/localProjects.ts`, `Frontend/src/server/jwt.ts`, `Frontend/src/server/proxy.ts`, `Frontend/src/server/proxy.test.ts` (and a `jwt` test if one exists).
`server/*` is the Cloudflare Pages Function (deploys with the site). Keep it dependency-free (WebCrypto + fetch only).

## 1. Project polling (FE-09)
`useProjects.ts` starts a new six-worker pool every 15 s even if the last one is still running; workers keep requesting after unmount (`alive` only guards `setSnaps`);
an older `getLive` can overwrite a manual pause/resume (`setSnap`).
Fix with a pure helper in `pollPool.ts` (e.g. `runPool(items, limit, fn, isAlive)` that stops taking new items when `isAlive()` is false) and in the hook:
- a `running` ref: a tick that fires while a cycle is in flight is skipped;
- workers check `alive` before each request;
- per-id `changedAt` map: manual `setSnap(id, …)` records `Date.now()`; a `getLive` result for that id is applied only if its request started after `changedAt[id]`.
Tests: concurrency never exceeds the limit; `isAlive=false` stops new work; (logic-level) a result started before a manual change is ignored.

## 2. Atomic rename of uploaded files (FE-11)
`localProjects.ts` `renameLocal` reads in one transaction and writes in another, so a delete in between is undone. Do `get` then `put` inside **one** `readwrite`
transaction on the store; if the record is missing, do nothing. Fire the existing `changed()` notification after the transaction completes. In the shared `run()`/open helper,
close the DB on `onerror` and `onabort` as well as `oncomplete`. Extract the record-update step as a pure function and unit-test it (IndexedDB isn't available in Node).

## 3. Proxy hardening (N4)
`server/jwt.ts`: concurrent cold requests each fetch JWKS. Memoize the in-flight promise (one fetch shared by concurrent callers; clear it when it settles), and give the JWKS
fetch `AbortSignal.timeout(5000)`; on failure keep using the cached keys (current behaviour). Do NOT add a timeout to the origin fetch in `proxy.ts`.
Test: 10 parallel verifications on a cold cache → the JWKS loader is called once.

## 4. Proxy shared secret (pairs with backend BK5)
`ProxyEnv` gets optional `PROXY_SHARED_SECRET?: string`. When it is set (non-empty), the proxy adds header `x-proxy-secret: <value>` to the upstream request (alongside the
existing `x-user-id` and `authorization`). Never forward a client-supplied `x-proxy-secret` (the FORWARD allowlist already prevents it; add a test).
Tests in `proxy.test.ts`: secret set → header present upstream; unset → absent; client-sent `x-proxy-secret` is not forwarded.

## Done
Tests pass (`node --test src/server/proxy.test.ts src/app/report/pollPool.test.ts` plus any new ones); eslint/tsc clean for your files.
