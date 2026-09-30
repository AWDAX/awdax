# Paste this into the next agent

```
You are continuing the AWDAX web app. Repo: X:\Hackathons\Codecubicle\awdax\Frontend (React 19 + TypeScript +
Vite 8 + Tailwind v4), branch feature/app-workspace. The app is built: a ChatGPT-style workspace, a Power BI-style
dashboard, exact in-browser analytics, follow-up questions, file uploads, a projects report, Ask database and data
export (milestones M0–M8 done, 2026-09-28).

Before writing any code, read these in order:
1. handoff/HANDOFF.md: state, how to run everything, rules, decisions, gotchas
2. handoff/TASKS.md: what's done, "Waiting on the owner", and "Nice to have next" (start there unless the owner
   asks for something else)
3. docs/APP.md: screens, data flow and the backend facts the app depends on
4. AGENTS.md and docs/DESIGN_SYSTEM.md: code style and the visual system

Hard rules:
- NEVER edit anything in X:\Hackathons\Codecubicle\awdax\Backend. The backend is read-only; work around it in the frontend.
- Numbers must stay exact: use src/analytics (BigInt decimals), never float math, for anything shown or exported.
- No new npm packages without the owner's yes (exceljs is the only approved one).
- No raw hex colours outside src/styles/tokens.css. Files under 300 lines. Motion only via m.* (LazyMotion strict).
- Don't change landing-page copy (src/landing) without asking the owner.
- Never push, deploy or publish. Commit on feature/app-workspace; the owner pushes.
- Before calling anything done, all of these pass: npm run test, npm run build, npm run lint, and the hex check in
  HANDOFF.md. Look at the screen in a browser at 1536x864 and 390 wide with a clean console (npm run dev:agent
  opens /app without Google sign-in on port 5174; start the backend first).
- In the same commit as the code, update handoff/HANDOFF.md and handoff/TASKS.md.

Start with `git status` and `git log --oneline -12` in the repo.
Report as: DONE · VERIFIED · FAILED/UNVERIFIED · CURRENT · NEXT.
```
