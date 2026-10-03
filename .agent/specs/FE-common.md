# Common rules for every frontend spec (F1–F4)

Repo: `X:\Hackathons\Codecubicle\awdax-audit`, frontend in `Frontend/` (React 19, TS, Vite). Branch `fix/stability-pass`. Read `Frontend/AGENTS.md` first.
Findings with line references: `docs/audit/FRONTEND_FINDINGS.md`. The plan: `docs/audit/REMEDIATION_PLAN.md`.

- Other agents edit other files in this same checkout at the same time. **Edit only the files your spec lists.** If you believe another file must change, stop and report instead.
- Do not run `git add/commit/stash/checkout/reset` or anything that changes git state. The lead commits.
- No new npm packages. Code style: single quotes, no semicolons, `.ts`/`.tsx` extensions in imports, files under 300 lines, no raw hex colors.
- Put ordering/generation logic in a small **pure** module with a Node test beside it (pattern: `src/api/liveState.ts` + `liveState.test.ts`, `src/api/mergeRows.ts`).
  Tests run with `node --test <file>` (Node 24 strips TS types; avoid TS-only syntax that needs transpiling: no enums, no namespaces, no parameter properties).
  A test file must not import a module that reads `import.meta.env` at load time (`src/api/client.ts`, `src/app/auth/supabase.ts`) — keep pure modules free of those imports.
- Write the failing test first, see it fail against the old logic where practical, then fix.
- Checks you run: `node --test <your test files>`, then `npx eslint <your files>` from `Frontend/`, then `npx tsc -b` from `Frontend/`.
  `tsc` may show errors in files other agents are editing; report errors only in your files, and make sure yours are zero.
  Do NOT run `npm run build` or `verify.mjs` (the lead runs the full gate after integration).
- Keep: row-id dedupe (`mergeRows.ts`), pathname remounting in `Layout.tsx`, per-instance tagged state in `useLiveStream`, React-escaped error text, the proxy's JSON error rewrite.
- Report back: each file changed with a one-line why, test names and pass counts, eslint/tsc result for your files, and anything you skipped.
