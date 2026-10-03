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

## Q4 — Backend: retire the legacy pre-React API and the old root page

Verified 2026-10-03 05:39 against code `931f7b734a43`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 05:38
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 05:39
  - routes: /app, /, /app/demo/*
  - viewports: mobile, desktop
  - states: default
  - 35 assertion(s) · 0 console error(s) · 0 failed request(s)

## Q5 — Backend: one shared Selenium import, dependency list trimmed

Verified 2026-10-03 05:40 against code `b7e5b01c9bb2`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 05:40

## Q6 — Backend: scrape sources in parallel, database writes serialized

Verified 2026-10-03 06:02 against code `51b508456861`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 06:01

## Q7 — Frontend: no Untitled chat flash while a chat loads

Verified 2026-10-03 06:05 against code `c3e3ce341a4f`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 06:04
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 06:05
  - routes: /app, /, /app/demo/*, /app/c/*
  - viewports: mobile, desktop
  - states: default
  - 48 assertion(s) · 0 console error(s) · 0 failed request(s)

## Q8 — Frontend: measure bundles, lazy-load what slows first paint

Verified 2026-10-03 06:10 against code `3a497929fa35`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 06:10
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 06:10
  - routes: /app, /, /app/demo/*, /app/c/*
  - viewports: mobile, desktop
  - states: default
  - 48 assertion(s) · 0 console error(s) · 0 failed request(s)

## Q9 — Backend: split scraper.py and RegulatoryFeed.py into smaller modules, no behaviour change

Verified 2026-10-03 06:14 against code `1b48e6b74ffb`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 06:14

### Q6 — later note (finding) · 2026-10-03 06:21

Same-source A/B of the scrape fetch+extract step (6 cars sources, same hour): SCRAPE_WORKERS=3 wall 482 s / 44 rows; =1 wall 655 s / 30 rows. 26% less wall time, not ~3x: NVIDIA serves concurrent calls slower (sum of per-source times 655 -> 1050 s) and 90 s read timeouts dominate both runs. One sample each; directional.

## Q12 — Apply the re-audit cuts: dead html_extract extractors + dev CLIs + unused service methods, write-only LiveBridge map, duplicate helpers, unused frontend exports

Verified 2026-10-03 09:45 against code `4065e34c7ae6`.

- **code** — PASS via `verify.mjs` · recorded 2026-10-03 09:44
- **ui** — PASS via `playwright-core+chromium-1243 (headless)` · recorded 2026-10-03 09:45
  - routes: /app, /, /app/demo/*, /app/c/*
  - viewports: mobile, desktop
  - states: default
  - 48 assertion(s) · 0 console error(s) · 0 failed request(s)
