# AWDAX app (`/app`)

The signed-in app, built on the existing FastAPI backend (`awdax/Backend`, github.com/AWDAX/awdax). **The backend is
read-only for frontend work**: every gap below is worked around here, never patched there.

## Screens and routes

| Route | Screen | Main files |
|---|---|---|
| `/app` | New chat: prompt box (text, voice, file), shortcut strip, Try cards | `src/app/chat/NewChat.tsx`, `src/app/prompt/PromptBox.tsx` |
| `/app/c/:id` | A web request: thread, live run, dashboard, questions | `src/app/chat/ChatPage.tsx`, `LiveRun.tsx`, `Thread.tsx`, `ChatData.tsx` |
| `/app/f/:id` | An uploaded file: dashboard and questions | `src/app/chat/FilePage.tsx`, `src/app/files/*` |
| `/app/projects` | Projects report | `src/app/report/*` |
| `/app/ask` | Ask database (off for everyone for now: `src/app/features.ts`) | `src/app/ask/AskPage.tsx`, `ProjectAsk.tsx` |
| `/app/dev` | Dev builds only: component gallery and the dashboard on sample tables | `src/app/dev/DevPreview.tsx` |

The sidebar (`src/app/workspace/`) lists every web request and uploaded file, grouped by day, with search and a
⋯ menu per chat: Rename (web names are kept in this browser; the backend has no rename) and Delete, with a few
seconds to undo.

## How data flows

1. **New web request.** `POST /api/instances`, then `POST /api/instances/{id}/messages` with the sentence. The backend
   scrapes in the background and streams progress over SSE (`/live/stream`, see `src/api/useLiveStream.ts`).
2. **Rows arrive** as `dataset` in the stream: `{ columns: string[], rows: string[][] }`. Every cell is text.
3. **`profileTable()`** (`src/analytics/profile.ts`) reads each column as number, money, percent, period, category,
   URL or text. It parses every cell exactly (BigInt decimals: Indian and Western grouping, ₹/$/€/£, lakh/crore,
   K/M/B, units, "N/A" as missing, never 0) and lists each cell it couldn't read, with the reason.
4. **`runQuery()`** (`src/analytics/aggregate.ts`) powers every chart, answer and export: filter, group,
   count/sum/avg/median/min/max/distinct, sort, top N plus Other. Averages round half-to-even at a stated scale.
5. **Questions** (`src/analytics/ask.ts`, `answer.ts`) turn plain English into a query and a sentence. They never
   call the backend: `POST /messages` would replace the goal and wipe the dataset.
6. **Uploads** (`src/app/files/readFile.ts`): CSV, TSV, JSON and XLSX are read in the browser into the same table shape
   and kept in IndexedDB (`localProjects.ts`). PDF and Word tables are refused with a clear reason.

## Dashboard page and sources

- The Report tab is one screen: a 12 × 6 grid sized to the viewport (number cards on top, up to six charts). Tiles resize
  in page rows and columns; "Fit to one screen" re-packs them. Data and Sources are separate tabs.
- Charts place time by real time (gaps show), group dates by month, quarter or year, and label exact values where they fit.
- Sources come from three places, so no sources endpoint is needed:
  - the bot's first-pass report, parsed by `src/analytics/runReport.ts`;
  - the rows' `source_url` column, which gives exact rows per site;
  - the live stream's `current_source`, which lists the pages read.

## Backend facts the app depends on (checked against the code)

- One goal per instance: a new message resets the dataset. So there's one request per chat, and follow-ups stay in the browser.
- Times come without a timezone (SQLite drops it). Always use `apiDate()` from `src/api/dates.ts`.
- `GET /api/instances` has no status or rows. The report polls `/live` per project, six at a time, every 15 s.
- `PATCH /live` doesn't push an SSE event. The UI reads `/live` back after pausing or resuming.
- No CORS: in dev, Vite proxies `/api` and `/health` (`vite.config.ts`). In production the Pages Function
  `functions/api/[[path]].ts` (`src/server/proxy.ts`) forwards `/api/*` to the backend. Setup: `docs/CONNECT_BACKEND.md`.
- No auth on the backend: every signed-in user sees every instance. The production proxy lets only signed-in users
  through (optionally only listed emails), checking the Supabase token itself (`src/server/jwt.ts`).
- When the stream is buffered (a Cloudflare quick tunnel does this), `useLiveStream` notices within 8 s and polls `/live`,
  reloading the table and chat whenever the rows, phase or cycle change.
- Real scraping needs `GEMINI_API_KEY` in `Backend/.env`.

## Kept in this browser (localStorage / IndexedDB)

| Key | What |
|---|---|
| `awdax.dashboard.<id>` | A chat's tiles and layout (`file-<id>` for uploads) |
| `awdax.answers.<id>` | Questions asked; the numbers are recomputed from the current table on every load |
| `awdax.alerts` | Which projects alert on new rows, and the row count last seen |
| `awdax.sidebar.collapsed` | Sidebar state |
| IndexedDB `awdax/projects` | Uploaded files' tables |

## Checks

```bash
npm run test             # exactness tests for parsing, queries, answers and CSV
npm run build
npm run lint
npm run dev:agent        # http://localhost:5174, /app without Google sign-in (dev only)
```
