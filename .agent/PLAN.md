# PLAN — AWDAX

> **Responsibility:** what we are building and in what order.
> Authored by you and the agent together. The only file here that is written
> by hand. Tasks in `loop` should mirror this.

## Goal (phase from 3 Oct 2026: quality pass to 8.5/10)

Raise the codebase from ~6.5/10 (frontend 8, backend 5, results 5) to 8.5/10, and make runs faster and leaner, without breaking
production. Driven by `/ponytail-audit` (3 Oct): cut what is dead or over-built, make the slow parts fast, then audit again.
Owner (3 Oct): "start … keep going until you reach the goal like a loop … we don't change the tech stack (no SQLite → Postgres)".

## Constraints

- Same stack: Flask + SQLite + Selenium + NVIDIA/Gemini backend; React + Vite + Tailwind frontend. No new packages.
- Nothing may break production: every task keeps the backend suite (172 tests), the frontend gate and a real local run green.
  The root `verify.mjs` only compiles Python here, so each task also records the backend unittest run and `Frontend` verify.
- Backend changes are allowed (owner, 2 and 3 Oct), small and tested. Agents never push, deploy or touch production.
- Product behaviour stays the same unless a task says otherwise; files under 300 lines where a task touches them.

## Out of scope (owner decisions or stack changes)

- Counting or labelling the backend's "reference" rows differently (product decision).
- Replacing the deprecated `google-generativeai` SDK with REST: no `GEMINI_API_KEY` locally, so it can't be verified.
- Dropping `pdfminer.six`: it is the PDF fallback for eGazette runs, which can't be tested here.
- Postgres, Sentry (new account + package), plan caching across runs (changes freshness).

## Tasks

| ID | Task | Depends on | UI? | Type |
|----|------|-----------|-----|------|
| Q1 | Backend: delete verified dead functions and unused imports | — | no | — |
| Q2 | Frontend: delete CallChip and unused exports | — | yes | — |
| Q3 | Frontend: remove the switched-off Ask database page (chat's Ask box stays) | Q2 | yes | — |
| Q4 | Backend: retire the legacy pre-React API and the old root page | Q1 | no | — |
| Q5 | Backend: one shared Selenium import, dependency list trimmed | Q4 | no | — |
| Q6 | Backend: scrape sources in parallel, database writes serialized | Q5 | no | — |
| Q7 | Frontend: no "Untitled chat" flash while a chat loads | Q3 | yes | — |
| Q8 | Frontend: measure bundles, lazy-load what slows first paint | Q7 | yes | — |
| Q9 | Backend: split scraper.py and RegulatoryFeed.py into smaller modules, no behaviour change | Q6 | no | — |
| Q10 | CI at the repo root: backend tests + frontend gate on every PR | Q9 | no | — |
| Q11 | Re-run /ponytail-audit, rate the codebase, update docs/HANDOFF.md | Q10, Q8 | no | — |

## Previous phase (2 Oct): frontend audit remediation

Tasks A1–A9 were done on branches `fix/fe-*` and `fix/stability-pass` and merged into `main` as AWDAX/awdax PR #4 (e824f6c), outside
this board; A7 (per-user file storage) still waits on the owner. Details: `docs/audit/REMEDIATION_PLAN.md`, `docs/HANDOFF.md`.
