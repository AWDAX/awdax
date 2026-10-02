# AWDAX audit and remediation pack

**Date:** 2 October 2026 · **Baseline:** `main` @ `6fc90ba` · **Compared with:** `origin/frontend` @ `92130ba`
**Source:** https://github.com/AWDAX/awdax · **Input:** `##Documentation_Fixes.zip` (5 reports, 33 screenshots)

## Read in this order

1. [CLAIM_VALIDATION.md](CLAIM_VALIDATION.md): each ZIP claim marked true, partial, false or unproven, with file:line evidence.
2. [FRONTEND_FINDINGS.md](FRONTEND_FINDINGS.md): races and lifecycle bugs in `Frontend/`, ranked, with fixes. Checked by two independent passes.
3. [REMEDIATION_PLAN.md](REMEDIATION_PLAN.md): batches, files, dependencies, rollback, and the decisions we need from you.
4. [VERIFICATION_PLAN.md](VERIFICATION_PLAN.md): how each batch is proven, with browser scenarios that need no backend.
5. [AGENCY_WORKFLOW.md](AGENCY_WORKFLOW.md): Opus plans and reviews, Sonnet implements, Haiku verifies.
6. [ARCHIVE_INVENTORY.md](ARCHIVE_INVENTORY.md): every file in the ZIP and which claim it supports.

## What changes the picture

- **Frontend deadlocks: none found.** The real frontend problems are races (stale responses overwriting newer state)
  and lifecycle leaks (the microphone staying on after leaving a chat).
- **User isolation is not in place**, despite what the reports say. Most per-chat API routes ignore the user. The backend trusts any caller's
  `X-User-Id` header and falls back to unverified JWT decoding. This is the most urgent item; it is backend work (B1).
- **"Merge `frontend` to fix production" is mostly moot.** 14 of the 19 listed commits are already on `main`; only 5 are branch-only,
  and merging them conflicts in 3 files.
- **WAL is not a proven cure for the 524s.** A locked SQLite database fails in 5 s; a 524 means 100 s of silence. That needs backend logs.
- **The sidebar HTML bug** can only reach users who bypass the Pages proxy, which already rewrites gateway errors. If production shows it,
  production isn't using the proxy, and the identity problem above is directly exposed.
- **The "trimmed mean" is never used**, and range midpoints exist only on the branch.

## Evidence

- `npm ci` from the lockfile (you approved it): exit 0, no package changes.
- `verify.mjs` on `main`: **PASS** for lint, types, build and tests (`.agent/evidence/baseline-verify.json`).
- Not done: browser reproduction, backend tests, any production request. The baseline does not prove the races are absent.

## Boundary

This pack is a proposal. No application source has changed. Approving a batch starts implementation on its own branch.
Pushing, deploying and every backend change stay with you.
