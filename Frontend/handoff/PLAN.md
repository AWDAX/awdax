# AWDAX app: chat workspace, dashboards, projects report, ask-your-data

## Context

The FastAPI backend (`awdax/Backend`, from github.com/AWDAX/awdax) works and is **read-only for us**. We don't
touch its code, config or logic. The frontend (`awdax/Frontend`, React 19 + Vite + Tailwind v4, Google sign-in
already gating `/app`) has only a placeholder `AppShell`. We build the signed-in app on top of the backend's 9 endpoints + SSE:
a ChatGPT-style workspace where each prompt becomes a tracked scrape, then a Power BI-style dashboard the user
shapes, follow-up questions answered exactly from the scraped data, a projects report, and exports.

### What the backend docs get right, and what they miss (checked against the code)
- Endpoints, payloads and the SSE format match `api/routes/*.py`. `/docs` works locally.
- **One goal per instance.** `append_user_message` (`warehouse/instances.py`) replaces `goal_text` and **wipes
  the dataset** on every new message. The docs call it a "conversational thread". It isn't one. So after the first
  prompt the chat input goes away, and follow-ups never call `POST /messages`.
- `table` also carries `name` and `source_url` (it is `ExtractedTable`); **every cell is a string** ("144,879"),
  so all numbers must be parsed on the client.
- No endpoint for follow-ups, Q&A, chart choice or export. All of that is frontend work.
- `GET /api/instances` has no status or row count, so the projects report needs one `/live` call per instance.
- No CORS and no auth. We can't add CORS, so in dev a **Vite proxy** handles it. Production needs a
  same-origin rewrite or the backend team adding CORS. Any signed-in user sees every instance.
- Bot messages are Markdown (`**Live**`, `_…_`). The doc's `request()` snippet overwrites custom headers.
- No per-cell receipts (only a table-level `source_url`, sometimes a `Source` column) and no plan-approval step,
  so docs/PRODUCT.md principles 1–2 can't be met yet. The UI shows what exists and doesn't pretend.
- Real runs need `GEMINI_API_KEY` in `Backend/.env`. It is **currently empty**.

## Decisions (owner answers, 2026-09-27)
- Ask-database and follow-ups: **in-browser, exact** engine over `GET /api/instances/{id}/dashboard` data.
- Follow-ups are answered from the stored dataset (the DB API). They never start a new scrape. New data = **New chat**.
- Export is **data only**, never dashboard pictures: SQL, JSON, CSV, Excel and more (see M6). The one new package
  is `exceljs`, for real typed .xlsx, loaded only when someone exports. Installing it is part of approving this plan.
- Charts follow DESIGN_SYSTEM: ink series, yellow wash, grey ramp, no rainbow. This deviates from PRODUCT.md
  ("not a BI tool", "max 4 charts"): auto-suggest stays at 4, and the user can add more. PRODUCT.md gets updated to match.

## Owner-required design assets: where each one goes (and the feature built for it when none exists)
Sources were checked on 2026-09-27.
- React Bits "Micro" TS-TW registry, `DavidHDev/react-bits` `public/r/*-TS-TW.json`. Licence: MIT + Commons
  Clause, allowed by the frontend AGENTS.md.
- ncdai copy-button: MIT.
- The OdysseyUI avatar repo has **no licence file**, and it uses gradients and shadows, which DESIGN_SYSTEM bans. We
  rebuild its behaviour (an assistant orb with blinking eyes) in house style and don't copy the code.

Adaptation rules for every asset. Each lives in `src/ui/micro/` and gets a credit in CREDITS.md.
- Swap `@hugeicons/*` for our `src/ui/icons.tsx`, so hugeicons isn't installed.
- `motion.*` becomes `m.*` (the app uses LazyMotion strict).
- Colour props default to tokens, never raw hex.
- The 4px radius replaces pill shapes. VoicePill already has `shape='rounded'`.
- Slow timing from DESIGN_SYSTEM, a reduced-motion fallback, and files split to stay under 300 lines.

| Asset | Where it's used | Feature built for it |
|---|---|---|
| **VoicePill** | Mic in the New-chat composer and the Ask box | **Speech-to-text**: `useSpeechToText.ts` (Web Speech API, `webkitSpeechRecognition`, en-IN/en-US). Interim text streams into the input, and the waveform uses its `reactive='mic'` mode. On unsupported browsers the mic is disabled and says why. |
| **ThoughtLine** | The live run line in the chat, e.g. "Searching sources…" with the phase steps | Driven by SSE `phase`/`detail`. It settles to "First pass done in 2m 14s" once `dataset` arrives. |
| **CallChip** | One chip per pipeline step (search, file, terminal, edit icons), with the current source domain as its argument | Status comes from the phase. On `error`, `onRetry` re-arms tracking (PATCH live off, then on). |
| **SwipeToast** | App-wide toast host | New-rows alerts, export done, copied, errors, and undo for delete. |
| **BellToggle** | Chat header and each row in the projects report | **Row alerts**: when a watched project adds rows (SSE, or report polling on `rows_added_last_cycle`), show a toast, plus a browser Notification if permission is granted. The badge counts unseen new rows. Settings are stored in localStorage. |
| **FuseButton** | Delete chat/project, pause tracking, reset dashboard layout | The destructive call runs only on fuse end, so there's an undo window before `DELETE`. |
| **CopyButton** | Bot messages, answer cards, table cells, generated SQL, share link | `useCopyToClipboard` with done and error icon swap. Uses our Button, not shadcn or lucide. |
| **Avatar orb** | Assistant avatar on bot messages and in the empty state | Blinks and "breathes" while a run is working; still when idle. The user avatar stays the Google photo. |

## Work location
`awdax/Frontend`, new branch `feature/app-workspace` from `phase-1`. Commit per milestone; the owner pushes.
Code style: single quotes, no semicolons, `.ts(x)` imports, files <300 lines, tokens only (no raw hex).

## Handoff for the next agent (made first, updated after every milestone)
`awdax/Frontend/handoff/`:
- `README.md`: how to use this folder.
- `HANDOFF.md`: state, how to run backend and frontend, rules (backend is read-only), decisions, gotchas.
- `TASKS.md`: milestone checklist with status and the exact next step.
- `CONTINUE_PROMPT.md`: a paste-ready prompt for ChatGPT Astra: "read handoff/, continue from TASKS.md".
It stays current at every commit, so work can stop at any point. At the end, a final state and prompt get written.

## Milestones

**M0: Plumbing.** Handoff folder. `vite.config.ts` proxy: `/api` and `/health` go to `AWDAX_API` (default `http://127.0.0.1:8000`).
- `src/api/types.ts`: backend contract plus `name`/`source_url`. `domain/types.ts` stays untouched.
- `src/api/client.ts` and `src/api/awdax.ts`: typed services.
- `src/api/useLiveStream.ts`: EventSource with reconnect, falling back to polling `/live` every 5 s.
- `src/api/InstancesProvider.tsx`: list, refresh on focus and every 20 s, optimistic delete.

**M1: Workspace shell (ChatGPT layout).** `src/app/workspace/`:
- `Layout.tsx`: the sidebar plus an outlet. It replaces the placeholder `AppShell`, and sign-out moves into the sidebar user menu.
- `Sidebar.tsx`: New chat, search chats, links to Projects report and Ask database.
- `HistoryList.tsx`: every instance, grouped Today / Yesterday / Previous 7 days / Older, with a status dot, and
  delete behind a confirm step. Collapsible on desktop, a drawer on mobile.
- Routes in `AppRoot.tsx`: `app` = NewChat, `app/c/:id` = ChatPage, `app/projects`, `app/ask`.

**M1b: Micro assets.** Port the eight assets into `src/ui/micro/` using the adaptation rules above, add
`src/app/voice/useSpeechToText.ts` and the toast host, and credit each one in CREDITS.md. Check each one at 1536×864 before wiring it in.

**M2: Chat page.**
- `NewChat.tsx`: centered composer and example prompts. Sending runs `createInstance` then `sendMessage`, and
  navigates to `/app/c/:id`, where **the input bar is gone**.
- `ChatPage.tsx`, `Thread.tsx`, `Markdown.tsx`: a tiny safe renderer for bold, italic, links, lists and code, with no raw HTML.
- `LiveRail.tsx`: phases discovery → inspect → extract → merge → sleep, plus detail, current source, rows and cycle.
  It also holds Pause/Resume (`PATCH /live`) and error state.
- The dashboard mounts once `dataset` arrives. On `chat_updated`, refetch the instance.

**M3: Exact analytics core.** `src/analytics/`, pure TypeScript, tested with `node --test` (Node 24 strips types, so no new package):
- `decimal.ts`: BigInt-scaled decimals, so sums, averages and percentages are exact. Averages use half-even rounding at the shown precision.
- `parse.ts`: ₹/$/€/Rs/INR, Western and Indian grouping (`1,44,879`), `(12)` negatives, `%`, K/M/B/Cr/lakh
  suffixes. Missing tokens (`N/A`, `—`, empty) never become 0. Periods: ISO, `2024-01`, `Jan 2024`, month names, `Q1 2024`, years.
- `profile.ts`: column type (number, money, percent, period/date, category, url, text), unit, and each unparsable cell (row + raw text).
- `aggregate.ts`: group by, then count/sum/avg/min/max/median/distinct. Top N plus Other, chronological period sort, filters.
- `suggest.ts`: up to 4 suggested charts, each with a reason, and follow-up questions built from the profile.
- `ask.ts`: parses common phrasings ("highest X", "total X by Y", "average X in 2024", "trend of X", "compare A vs B",
  "how many rows where…") into a structured query. Anything else opens the query builder.

**M4: Dashboard (Power BI style).** `src/app/dashboard/`:
- `charts/`: hand-built SVG in the existing `src/product/chart/*` style: column, bar, line, area, donut/pie, scatter, KPI card and table tile.
  Tooltips show exact values, with an optional data-labels toggle.
- `ChartPicker.tsx`: the suggested charts as a checklist the user picks from.
- `ChartBuilder.tsx`: pick type, X field, measure, aggregation, sort, top N and filter.
- `Grid.tsx`, `Tile.tsx`, `useLayout.ts`: a 12-column grid. Tiles resize by dragging the corner (snaps to columns
  and rows), move with a drag handle, and have keyboard move/resize commands in the tile menu. Layout is saved in
  localStorage per instance, with a Reset option.
- `Slicers.tsx`: category multi-select, period range and a global search. They apply to every tile, and clicking a bar cross-filters the rest.
- `DataGrid.tsx`: sort, search, per-column filter and pagination over the full table.
- Precision note under every tile: "Sum of X by Y · 24 rows used · 2 excluded", with a list of the excluded rows,
  and a "View exact values" table.

**M5: Follow-ups and Ask database.**
- `FollowUps.tsx`: chips under the dashboard, generated from the data.
- Clicking a chip, or asking, gives an `AnswerCard`: the exact answer sentence, a mini chart, the rows used and
  **Add to dashboard**. Answers are saved per instance in localStorage and shown in that chat's thread.
- `src/app/ask/AskPage.tsx`: pick any project that has data, ask in words or use `QueryBuilder.tsx`, and pin the result to that project's dashboard.
- An "Ask this data" button on the chat page opens the same panel for the current dataset.

**M6: Data export.** `src/app/export/`, one small writer per format.
- **SQL**: `CREATE TABLE` plus batched `INSERT`s, for PostgreSQL, MySQL, SQLite and SQL Server. Column types come
  from the profile (NUMERIC/DECIMAL with exact scale, DATE, TEXT), identifiers are quoted, strings escaped, and missing values become `NULL`.
- **JSON**: an array of objects, with typed numbers and ISO dates, or the raw strings if the user picks that.
  **JSON Lines** as well.
- **CSV**: UTF-8 with a BOM, so it opens in Excel and Power BI, with exact unformatted numbers. **TSV** as well.
- **Excel .xlsx** via exceljs (loaded with dynamic `import()`): a Data sheet with typed number cells, frozen header
  and autofilter, plus an About sheet (source URL, capture time, filters applied).
- **XML** and a **Markdown** table.
- Scope picker: the whole dataset, the current filtered view (slicers and search), or a tile's aggregated table.
  Choose between parsed values and the raw text the scraper returned.
- `ExportMenu.tsx` sits on the dashboard, each tile, DataGrid, AnswerCard and each projects-report row. Filenames follow `<project-title>_<yyyy-mm-dd>.<ext>`.

**M7: Projects report** (`src/app/report/`):
- One row per instance: title, status badge (live / sleeping / running phase / paused / error / idle), rows,
  current source, cycle, created, updated, and actions (open, pause/resume, export CSV, delete).
- KPIs across the top: projects, live now, total rows, errors.
- A **search bar**, **filter buttons** (All, Live, Paused, Error, Has data, Empty) and **query buttons**
  (Most rows, Updated today, Failed, Never ran), plus sort.
- `useProjectStatuses.ts` fetches `/live` for each instance, 6 at a time, and refreshes every 15 s.

**M8: QA and docs.**
- `docs/APP.md` (screens and backend-contract notes) and a PRODUCT.md update.
- Reviewer agent pass, then fixes.
- Final HANDOFF, TASKS and CONTINUE_PROMPT.

## Verification (every milestone, before its commit)
- `npm run build`, `npm run lint`, `node --test src/analytics`, the hex check
  (`rg "#[0-9a-fA-F]{3,8}\b" src -g "!styles/tokens.css"` prints nothing), and `node ~/.agents/gates/verify.mjs` prints PASS.
- Runtime: backend `.\.venv\Scripts\python.exe app.py` (port 8000) and `npm run dev` (5173). Playwright MCP at 1536×864
  (the owner's screen) plus 1440, 1024, 768 and 390, and once with reduced motion, with a clean console. Checks:
  create a chat, the composer disappears, SSE phases update, the dashboard fills, charts are added, resized and moved,
  a follow-up is answered, and the projects report filters and searches. For exports, every format downloads.
  The SQL runs in `sqlite3` and matches the row count. The JSON parses. The .xlsx opens with number cells. The CSV opens in Excel with ₹ intact.
- Voice: Playwright checks the unsupported and permission-denied states. Real speech-to-text needs the owner to try it once in Chrome or Edge,
  because the Web Speech API sends audio to the browser vendor's service and can't be automated.
- Precision: unit tests on the parse and sum cases (Indian grouping, crore, %, N/A). Each chart total is checked against the DataGrid by hand.
- End-to-end scraping needs `GEMINI_API_KEY` in `Backend/.env` (the owner sets it). Until then, the UI is
  checked on analytics fixtures in tests plus a real backend run for the list, create, SSE and delete paths.
