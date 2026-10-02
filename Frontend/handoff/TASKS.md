# Tasks

Legend: `[x]` done and verified · `[~]` in progress · `[ ]` not started. Details for each milestone are in PLAN.md.

**Next step:** All milestones (M0–M8) are done. Start at "Nice to have next" below, or pick up whatever the owner
asks for. "Waiting on the owner" lists what agents can't do.

## M0: Plumbing
- [x] Branch `feature/app-workspace`, handoff folder
- [x] `vite.config.ts` proxy for `/api` and `/health` to `AWDAX_API` (checked: /health, /api/instances and SSE all pass through)
- [x] `src/api/types.ts`, `client.ts`, `awdax.ts`, `useLiveStream.ts`, `instancesContext.ts` + `InstancesProvider.tsx`, `dates.ts`
- [x] `npm run test:analytics` script

## M1: Workspace shell
- [x] `src/app/workspace/Layout.tsx`, `Sidebar.tsx`, `HistoryList.tsx` (grouped by date, search, delete with confirm), `PageHeader.tsx`
- [x] Routes: `/app`, `/app/c/:id`, `/app/projects`, `/app/ask` (the last three are placeholders). Sign-out is in the sidebar
- [x] `npm run dev:agent` preview without sign-in; `src/ui/appIcons.tsx`
- [ ] Later: a status dot per history item (after M7's statuses hook); swap the delete confirm for FuseButton (M1b)

## M1b: Micro assets (`src/ui/micro/`, credited in CREDITS.md)
- [x] VoicePill + `src/app/voice/useSpeechToText.ts` + `VoiceInput.tsx`
- [x] ThoughtLine, CallChip, SwipeToast + `src/ui/toast/` (ToastProvider is mounted in Layout), BellToggle, FuseButton, CopyButton, AssistantOrb
- [x] Gallery at `/app/dev?view=micro` (dev builds only)
- [ ] Wire-up still to do: FuseButton for delete in HistoryList; BellToggle row alerts (M7); VoiceInput in NewChat (M2)

## M2: Chat page
- [x] ChatPage: header (BellToggle row alerts, Pause via FuseButton, Resume, Delete via FuseButton), Thread + Markdown,
      LiveRun (ThoughtLine + CallChips from SSE), ChatData (dashboard + questions) once rows arrive
- [x] Verified against the real backend: create → start → live stream → error state ("GEMINI_API_KEY is not set")
- [x] **Owner redesign (2026-09-28)**: NewChat looks like ChatGPT's start screen: a big PromptBox (text, voice, + attach),
      a strip under it, and "See what AWDAX can do" cards with Try. The same PromptBox sits under the dashboard for
      follow-ups, with question chips. This replaces the earlier "input disappears" idea.
- [x] File uploads (CSV, TSV, JSON, XLSX) are read in the browser (`src/app/files/`), kept in IndexedDB, and opened at
      `/app/f/:id` with the same dashboard and questions; they show in the history with a file icon. A question typed with
      the file is answered first. PDF/Word tables are refused with a clear reason (no backend support).

## M3: Analytics core (`src/analytics/`, tests)
- [x] decimal, parse, period, profile, aggregate, format, spec, suggest, ask, answer, fixtures; 16 tests pass

## M4: Dashboard (`src/app/dashboard/`)
- [x] SVG charts (column, bar, line, area, donut, scatter, number card, table), ChartPicker (suggested + build your own),
      ChartBuilder, Tile (drag grip to move, corner to resize, menu for keyboard), Slicers + cross-filter, DataGrid, PrecisionNote
- [x] Checked on sample tables at `/app/dev?view=dashboard&table=sales|cars` at 1536×864; console clean
- [ ] Still to check: 1024 / 768 / 390 widths and reduced motion (do it in M8)

## M5: Follow-ups and Ask database
- [x] FollowUps chips, AnswerCard (sentence, chart, precision note, add to dashboard, export, copy), AskBox (PromptBox),
      answers saved per chat in localStorage (`useAnswers`), recomputed from the current table on load
- [x] AskPage (`/app/ask`): pick any project with rows (web or file) and ask; "Build a query" opens the ChartBuilder
      and pins the result to that project's dashboard. Answers are shared with the project's chat (same localStorage key)

## M6: Data export (`src/app/export/`)
- [x] SQL (PostgreSQL, MySQL, SQLite, SQL Server), JSON, JSONL, CSV (BOM), TSV, XLSX (exceljs, lazy), XML, Markdown
- [x] Scopes: all rows, filtered rows, one chart's numbers (tile menu → Export this data), one answer (M5 uses `kind: 'answer'`)
- [x] Verified: all 8 download in the browser; the SQL runs in sqlite3 (sum and NULLs exact); the JSON parses; xlsx cells are numbers

## M7: Projects report (`src/app/report/`)
- [x] KPIs, search, filter buttons (with counts), quick-query buttons, sort, and row actions (open, alerts BellToggle
      with new-row badge, pause/resume, export, delete with FuseButton). `useProjects` polls `/live` six at a time every 15 s
- [x] Verified in the browser with 2 web projects + 1 uploaded file; the error filter and the quick queries return the right rows

## M8: QA and docs
- [x] Checked in Playwright at 1536×864, 1024, 768 and 390: no horizontal overflow, no console errors; reduced motion loads clean
- [x] Reviewer pass: no critical or blocking findings. Its two warnings are fixed: dialogs trap and restore focus,
      and the tile menu takes arrow, Home and End keys (`src/ui/useFocusTrap.ts`)
- [x] `docs/APP.md` written; `docs/PRODUCT.md` updated (dashboard decision, uploads, what isn't built yet)
- [x] `npm test` added (runs the 19 exactness tests); `verify.mjs` passes (lint, types, build, test)

## M9: Owner feedback, 2026-09-28 (done)
- [x] **One-screen report page, like Power BI**: 12 × 6 canvas sized to the viewport (`src/app/dashboard/layout.ts`,
      `useBox.ts`); number cards on top, up to 6 charts; "Fit to one screen" when tiles spill over; Full screen;
      tabs Report | Data | Sources. Layouts saved under `awdax.dashboard.v2.<id>` (tiles are 1–6 page rows)
- [x] **Precise charts**: timelines placed by real time (missing months are gaps, not joined; `period.ordinal`);
      dates grouped by month/quarter/year (`Query.bucket`, builder "Group dates by"); event dates count rows per
      period; exact value labels on by default where they fit (`scale.spaced`), exact tooltips everywhere;
      codes like "2W/4W" are categories, not numbers; the main measure is picked by name (units, sales, price…)
- [x] **Sources**: `src/analytics/runReport.ts` parses the backend's run report (validated/rejected sites, scores,
      access method, fill rate, strategies); `src/app/sources/` merges it with exact rows per site (`source_url`)
      and the pages read live (`useVisits`). Shown as a strip in the live run, a panel before the first pass, and the
      dashboard's Sources tab. The thread hides the report's copy of all rows
- [x] ~~Sample run at `/app/sample`~~ (removed 3 Oct 2026: nothing linked to it). The New chat cards now replay real
      recorded runs at `/app/demo/<slug>` (`src/app/demo/`)
- [x] ChatPage split into ChatView (drawing) + ChatPage (backend wiring); 28 tests

## M10: Functional and UI QA pass, 2026-09-28 (done)
Scripted Playwright checks (kept in `X:\Hackathons\Codecubicle\.playwright-mcp\qa-*.js`, rerun them after UI changes):
- [x] Dashboard: menus, type switch, value labels, edit, add, Fit to screen, drag resize, drag reorder, cross-filter,
      slicers, period range, search, the not-counted popover, Data sort and paging, Sources, export, reset
- [x] Follow-ups: chips, typed questions, unreadable-question hint, pin to dashboard, export, remove, kept after reload
- [x] Shell: New chat (empty send, Try, attach and remove a file), sidebar collapse, search, delete with undo,
      phone drawer; projects report filters, quick queries, pause/resume; Ask database answer, query builder, toast
- [x] No sideways scroll on any screen or tab at 390 and 768; menus and dialogs stay on screen; keyboard reachable
      with visible focus everywhere; clean console in a fresh session
- [x] Fixed: clipped tile menus (now `src/ui/Popover.tsx`), tiles overlapping the questions when they spill over,
      mixed axis units, fuse buttons stuck in "done", keyboard-unreachable upload buttons, donut legend and source
      cards overflowing on phones, silent microphone denial, and more (see commit messages)

## M11: Owner polish, 2026-09-28 (done, branch `feature/app-polish`)
- [x] Landing nav: one button, "Sign in" when signed out and "Open the app" when signed in
- [x] Voice: stops after 8 s with no words or 10 s after the last word, and says so; a browser 'network' error after a
      long quiet spell is reported as silence; the mic button resets when dictation ends by itself
- [x] Rename chats: ⋯ menu per history row (Rename, Delete with a 4 s Undo). Web names live in this browser
      (`src/api/chatTitles.ts`, the backend has no rename); file names in IndexedDB (`renameLocal`)
- [x] Styled Sort dropdown (`src/ui/Select.tsx`, reusable for the tile and Month selects too)
- [x] Prompt box: no + button (the strip's "Upload a file", drag and drop and paste remain); Send fades in
- [x] Strip: "Web requests refresh every 5 min" on the same line as the shortcuts
- [x] Sidebar open/close and the phone drawer slide (500 ms, ease-soft)
- [x] Dashboard: roomier tiles; KPI numbers no longer print over their note; y ticks thin out on short charts;
      axis labels spaced by their real anchors; value labels get a halo. Checked at 1536×730 and 1536×864
- [x] Ask database behind `FEATURES.askDatabase` (`src/app/features.ts`), off for everyone; `VITE_FEATURE_ASK_DATABASE=on`
      turns it back on
- [x] Chart colours: tile menu → Colour (7 tokens `chart-*`, one colour per chart, saved with the layout)
- [x] No scrollbars inside chart tiles (`scrollbar-none` in index.css; they still scroll)
- [x] Header actions are equal boxes (same height; same width on sm+, stacked on phones); BellToggle and FuseButton
      `md` now match buttonClass `md`; dashboard toolbar buttons all h-10
- [x] Page no longer scrolls behind the chat (sr-only tables escaped a non-positioned <main>); ask box pinned
- [x] "Add charts" opens on a picture gallery (Column, Bar, Line, Area, Pie, Donut, Scatter, Number card, Table); a pick
      opens the builder set up for that type (`chartTypes.ts` draftFor), with a live preview. New chart type: `pie`

## Waiting on the owner (not agent work)
- [ ] Put `GEMINI_API_KEY` in `Backend\.env`, then run one real request end to end (the dashboard has only been
      checked on sample tables and an uploaded CSV so far)
- [ ] Try voice input once in Chrome or Edge (the Web Speech API can't be automated)
- [x] Landing FAQ rewritten to match the built app (2026-09-28, on the owner's ask)
- [ ] Production: the app calls `/api` on its own origin. Add a same-origin rewrite to the HTTPS backend (for example
      a Vercel rewrite `/api/*` → backend), or have the backend team enable CORS and set `VITE_API_BASE_URL`
- [ ] Push `feature/app-workspace` and open the PR into `phase-1`

## Nice to have next (agent work, in this order)
- [ ] Node tests for the export writers (`src/app/export/formats.ts`, `sql.ts`, `scope.ts` are pure TS)
- [ ] A status dot per chat in the sidebar (reuse `useProjects` from `src/app/report/`)
- [ ] Per-tile filters in the ChartBuilder (the `Query.filters` field already exists)
- [ ] Tables inside PDF or Word uploads (needs a new package or a backend endpoint: ask the owner first)
