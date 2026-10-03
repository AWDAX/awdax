# Agency workflow

Your brief: plan with a strong model, implement with a cheaper one, review with a strong model again.
This is the team that runs it, and what each role may and may not touch.

## Roles

| Role | Model | Access | Job |
|---|---|---|---|
| **Lead** (main session) | Opus | Everything below, plus talking to you | Picks the next batch, briefs agents, integrates, commits on the batch branch, reports. Never pushes or deploys. |
| **planner** | Opus | Read-only | Turns one batch from REMEDIATION_PLAN.md into an exact spec: the pure module's API, the failing tests to write, the line-level hook changes, and what must not change. |
| **frontend** (implementer) | **Sonnet** | Edits only the batch's files, on its branch | Writes the failing test, then the fix, then runs the gate. Haiku only for one-line batches (FE-08, FE-12, N5). |
| **reviewer** | Opus | Read-only | Checks the diff against the spec and the finding. Walks every interleaving again, looks for regressions in the callers, enforces "Preserve while fixing". Approve or "changes". |
| **verifier** | Haiku | Read-only + runs gates/browser | Runs `verify.mjs`, the batch's browser scenarios and the regression smoke; saves reports under `.agent/evidence/`. Never fixes. |

Why not one model for everything: the race fixes are small in lines but easy to get subtly wrong. A strong model writes the spec
and judges the result. The cheaper model does the typing, where most of the tokens go.

## One batch, end to end

```
planner spec ─► frontend: failing test ─► fix ─► gate PASS ─► reviewer ─┬─ changes ─► frontend (max 3 rounds)
                                                                         └─ approve ─► verifier (gate + browser)
                                                                                         └─► Lead commits on fix/<batch>; you push
```

- Specs and reviews are saved in `.agent/` beside the evidence, so a new session (or a different tool) can pick up any batch cold.
- The implementer never reviews its own work, and the reviewer never edits.
- A third "changes" verdict stops the batch, and the Lead brings it to you with the reviewer's reasons.

## Running batches in parallel

A1, A2, A5 and A6 own disjoint files, so they can run at the same time, each on its own branch. A3 and A4 touch shared, central files
(`InstancesProvider.tsx`, `useLiveStream.ts`), so they run alone. Parallel work uses the loop's factory mode only after you raise `maxParallel` above 1.
Until then, batches run one after another.

## What stops the line and comes back to you

- Any backend change (Track B): your standing rule says the backend is read-only for agents.
- A7 (per-user storage): it decides what happens to people's uploaded files.
- `233fb40` (range midpoints in totals): a product decision.
- A new package, a change to more than 3 files outside the batch's list, or anything touching deploy config, keys or production.
- A reviewer finding that the plan itself is wrong.

## Cost control

- Exploration and reviews run inside subagents, so the main session's context stays small.
- The implementer gets the spec plus only the files it owns, not the whole audit.
- The verifier runs on the cheapest tier; the browser runs only the scenarios its batch owns plus the smoke list.

## Reporting to you

Each batch ends in five lines: DONE · VERIFIED · FAILED/UNVERIFIED · CURRENT · NEXT,
with the branch name ready for you to push.
