# AWDAX app: handoff

Last updated: 2026-09-28, by Claude (Opus 5.5), after M11 (owner polish: rename chats, voice silence handling, Ask database flagged off).
`docs/APP.md` is the product-level description of the app; this file is for whoever continues the build.

## What we're building (owner requirements)

The signed-in app at `/app`: a ChatGPT-style workspace on top of the existing AWDAX backend.
1. **Chat history sidebar.** Every request ever sent is a chat: a backend "instance", or an uploaded file.
2. **New chat looks like ChatGPT's start screen** (owner redesign, 2026-09-28):
   - A big prompt box: text, voice (speech to text), and **+ attach a data file**.
   - A strip of shortcuts under it, and "See what AWDAX can do" cards with **Try** buttons.
3. **A web request** shows the live scrape (ThoughtLine + CallChips), then a **Power BI-style dashboard** the user
   shapes: pick charts, build their own, resize, move, slicers, click-to-filter, export.
4. **Below the dashboard**: follow-up question chips plus **the same prompt box**, answered exactly in the browser from
   the rows. This replaced the earlier "input bar disappears" idea.
5. **Uploaded files** (CSV, TSV, JSON, XLSX) become a dashboard straight away, in the browser (the backend has no upload endpoint).
6. **Ask database**: question any project's data in words, by chips, or with a query builder. **Off for everyone**
   behind `FEATURES.askDatabase` (`src/app/features.ts`) while the owner decides whether to keep it.
7. **Projects report**: every project with status, rows, KPIs, a search bar, filter buttons and quick-query buttons.
8. **Data export**: SQL (four dialects), JSON, JSON Lines, CSV, TSV, Excel, XML, Markdown. Data only, no dashboard pictures.
9. **Owner-picked micro components**: VoicePill, ThoughtLine, SwipeToast, BellToggle, CallChip, FuseButton, CopyButton, and an avatar orb.

## Repos and folders

| Path | What | Rule |
|---|---|---|
| `X:\Hackathons\Codecubicle\awdax\Frontend` | This repo, github.com/AWDAX/Frontend. Branch `feature/app-workspace` from `phase-1` | Work here |
| `X:\Hackathons\Codecubicle\awdax\Backend` | FastAPI backend, github.com/AWDAX/awdax | **READ-ONLY. Never edit.** |
| `X:\Hackathons\Codecubicle` | Outer repo with only a first commit | Don't use |

## Run it

Backend (PowerShell 5.1: no `&&`, one command per line):
```powershell
cd X:\Hackathons\Codecubicle\awdax\Backend
.\.venv\Scripts\python.exe app.py        # http://127.0.0.1:8000, docs at /docs
```
The venv and Playwright Chromium are installed. Real scraping needs `GEMINI_API_KEY` in `Backend\.env`. It was
**still empty on 2026-09-28**. Without it, create, SSE, pause and delete all work, but discovery fails with
"GEMINI_API_KEY is not set" (the UI shows that error state correctly).

Frontend:
```powershell
cd X:\Hackathons\Codecubicle\awdax\Frontend
npm run dev          # http://localhost:5173, /app needs Google sign-in (the owner's)
npm run dev:agent    # http://localhost:5174, /app WITHOUT sign-in (dev only, for agents and Playwright)
```
The dev server proxies `/api` and `/health` to `AWDAX_API` (default `http://127.0.0.1:8000`), because the backend
has no CORS. Screenshots work best with Playwright MCP. Sample-data dashboard: `/app/dev?view=dashboard&table=cars`.

## Checks (all must pass before anything is called done)
```powershell
npm run test         # 19 exactness tests (parsing, queries, answers, CSV)
npm run build
npm run lint
rg "#[0-9a-fA-F]{3,8}\b" src -g '!**/tokens.css'   # must print nothing
node ~/.agents/gates/verify.mjs                     # Claude's gate; skip if it's missing on your machine
```
Then look at it in a browser at 1536×864 (the owner's laptop), 1024, 768 and 390, with a clean console.

## Backend contract (verified against the code)
- Endpoints: `GET/POST /api/instances`, `GET/DELETE /api/instances/{id}`, `POST /api/instances/{id}/messages`,
  `PATCH /api/instances/{id}/live`, `GET /api/instances/{id}/dashboard`, `GET /api/instances/{id}/live`,
  SSE `GET /api/instances/{id}/live/stream`. Types are in `src/api/types.ts`.
- **One goal per instance.** `POST /messages` replaces the goal **and wipes the dataset**. It's sent once, from New
  chat. Follow-ups and Ask never call it.
- `dashboard.table` = `{ name, source_url, columns: string[], rows: string[][], row_count }`. Every cell is a string.
- `GET /api/instances` has no status or rows, so the report polls `/live` per instance.
- `PATCH /live` doesn't push an SSE event; the UI reads `/live` back.
- Times come without a timezone. Always use `apiDate()` (`src/api/dates.ts`).
- There's no auth: every signed-in user sees every instance.

## Decisions (owner; don't reopen)
- The ask and follow-up engine is deterministic and in the browser (no LLM). Numbers are exact (BigInt decimals).
  Unreadable cells are listed, never counted as 0.
- Follow-ups answer from the stored rows and never re-scrape. New data means a new chat.
- Export is data formats only. The only new package is `exceljs` (lazy-loaded); hugeicons, radix and lucide are not installed.
- Charts are hand-built SVG in ink, yellow wash and grey ramp (DESIGN_SYSTEM.md). No rainbow.
- The start screen follows the ChatGPT layout the owner showed, in AWDAX's design system (not the pasted dark
  "ai-prompt-box"; its features were rebuilt on our primitives).

## Where things are
- `src/api/`: backend client (`awdax.ts`), `useLiveStream.ts`, `InstancesProvider.tsx`, `dates.ts`
- `src/analytics/`: the exact engine (`profileTable` → `runQuery`; `suggest*`; `parseQuestion` + `answer`; `csv.ts`) + tests
- `src/app/workspace/`: Layout, Sidebar, HistoryList (web + file chats), PageHeader
- `src/app/prompt/PromptBox.tsx`: the one prompt box (text, voice, files)
- `src/app/chat/`: NewChat, ChatPage, FilePage, ChatData (dashboard + questions), LiveRun, Thread, Markdown, alerts, useAnswers
- `src/app/files/`: readFile (CSV, TSV, JSON, XLSX), localProjects (IndexedDB), useLocalProjects
- `src/app/dashboard/`: Dashboard, Tile, TileMenu, charts/*, Slicers, DataGrid, ChartPicker, ChartBuilder, PrecisionNote, useDashboard
- `src/app/export/`: ExportDialog, scope (typed Sheet), formats, sql, xlsx, download
- `src/app/report/`: ProjectsReport, ProjectRow, reportFilters, useProjects, loadTable
- `src/app/ask/`: AskPage, ProjectAsk, AskBox, AnswerCard (flagged off: `src/app/features.ts`)
- `src/app/workspace/HistoryItem.tsx`: a history row with its ⋯ menu (Rename, Delete + Undo); `src/api/chatTitles.ts`
  keeps web-chat names in this browser
- `src/ui/Select.tsx`: the styled single-choice dropdown (Sort in the projects report)
- `src/app/sources/`: buildSources (report + exact rows per site + pages read live), SourcesPanel, SourceCard,
  SourcesStrip, useVisits
- `src/app/sample/`: SampleRun (`/app/sample`) and its script, in the backend's exact output shapes
- `src/app/chat/ChatView.tsx`: the chat screen from plain data (ChatPage wires the backend; SampleRun a script)
- `src/app/dashboard/layout.ts`: the 12 × 6 one-screen page (layoutPage, packedRows); `useBox.ts` measures it
- `src/analytics/runReport.ts`: parses the backend's run report text; `sampleRun.ts`: the sample report and rows
- `src/ui/micro/`, `src/ui/toast/`, `src/app/voice/`: the micro components (credits in CREDITS.md)
- `.claude/launch.json` (copied to `X:\Hackathons\Codecubicle\.claude\launch.json` for Claude's preview tool):
  `awdax-dev` (5173), `awdax-agent` (5174, no sign-in), `awdax-api` (8000)

## Gotchas
- **Invisible characters.** Some agent tools turn written escapes (backslash-u followed by 00a0, feff or 200b) into
  the real invisible character, and lint fails (`no-irregular-whitespace`). Check with `npm run lint`.
- `npm audit`: 2 moderate issues in `uuid`, pulled in by exceljs. The only offered fix is `--force` (breaking). Left as is.
- LazyMotion is `strict` in `src/main.tsx`. `motion.div` throws; use `m.div`.
- Lenis smooth-scrolls the window. Inner scroll areas need `data-lenis-prevent` (the app root has it).
- The owner's shell is Windows PowerShell 5.1.
- The landing FAQ (`src/landing/sections/Faq.tsx`) was rewritten on 2026-09-28, at the owner's request, to claim
  only what's built. The backend has no robots.txt check, no per-value receipts, no conflict resolution and no
  versioned monitors, so the FAQ doesn't promise them. Keep it that way. Don't change landing copy without asking.
