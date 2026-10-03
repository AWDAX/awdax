# PLAN — AWDAX

> **Responsibility:** what we are building and in what order.
> Authored by you and the agent together. The only file here that is written
> by hand. Tasks in `loop` should mirror this.

## Goal

The AWDAX web app (`Frontend/`) shows correct, current state under slow, failing or reordered network responses, and never keeps the microphone
or background requests running after the user leaves a screen. Every claim in the owner's ZIP is either fixed, refuted with evidence, or handed to the backend owner.
Details: `docs/audit/REMEDIATION_PLAN.md`.

## Constraints

- Baseline `main` @ `6fc90ba`; the gate passes there. Every batch keeps it passing.
- No new packages without the owner's yes. Files under 300 lines. One concern per branch.
- Backend Python is read-only for agents (Track B goes to the owner).
- Agents never push, deploy or change production, keys or Supabase settings.

## Out of scope

- Backend changes (B1–B4) unless the owner approves them explicitly.
- Merging `origin/frontend` wholesale; `233fb40` until the owner decides on midpoints.
- Redesign or visual changes beyond what a fix requires.

## Tasks

| ID | Task | Depends on | UI? | Type |
|----|------|-----------|-----|------|
| A1 | FE-02 + FE-07: honest API errors, no false "chat deleted" | — | yes | — |
| A2 | FE-10 + FE-12: microphone and dictation lifecycle | — | yes | — |
| A3 | FE-01: list request ordering across mutations | A1 | yes | — |
| A4a | FE-04: one state source for live callbacks | — | yes | — |
| A4b | FE-03/05/06/08: snapshot gate for the live dataset | A4a | yes | — |
| A5 | FE-09: single project-polling cycle | — | yes | — |
| A6 | FE-11: atomic uploaded-file rename | — | no | — |
| A7 | FE-13: per-user browser storage (owner decision first) | A6 | yes | — |
| A8 | N4 + N5: proxy JWKS/timeouts, auth gate catch | — | no | — |
| A9 | Sweep of the unchecked frontend files | — | no | — |

## Open questions

1. A7: per-user storage with migration, or clear on sign-out?
2. Track B: may an agent change the backend, or does the backend owner take B1–B4?
3. `233fb40`: may ranges count as midpoints in totals and averages? Separate robust average wanted?
4. Keep this clone at `awdax-audit/` or move it into `awdax/`? Which repo deploys production?
5. How is `awdax.synapical.com` hosted, and does it call `/api` through the Pages proxy?
