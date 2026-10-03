# QA — AWDAX

> **Responsibility:** what was checked, how, and what the result was.
> Append-only, written by the verification gates. This is the evidence trail:
> if a task is marked DONE, the proof is here.
>
> `STATUS.md` says *whether* something is verified. This says *how*.

Each entry records:

- the task and the code state it was verified against
- which classes ran — CODE, RUNTIME, UI
- the verdict per class: PASS / FAIL / UNVERIFIED
- for UI: console errors, failed requests, viewports, screenshots

`UNVERIFIED` is a real result. A check that could not run is never recorded
as passing.

---

## Q1 — Backend: delete verified dead functions and unused imports

Verified 2026-10-03 05:24 against code `00aa1c520ddb`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 05:24

## Q2 — Frontend: delete CallChip and unused exports

Verified 2026-10-03 05:30 against code `3697a3a54295`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 05:30
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 05:30
  - routes: /app, /, /app/demo/*
  - viewports: mobile, desktop
  - states: default
  - 35 assertion(s) · 0 console error(s) · 0 failed request(s)

## Q3 — Frontend: remove the switched-off Ask database page (chat's Ask box stays)

Verified 2026-10-03 05:33 against code `faed386b03da`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 05:33
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 05:33
  - routes: /app, /, /app/demo/*
  - viewports: mobile, desktop
  - states: default
  - 35 assertion(s) · 0 console error(s) · 0 failed request(s)
