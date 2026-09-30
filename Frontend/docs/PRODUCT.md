# AWDAX — Product

AWDAX turns a plain-English data request into a clean dataset where every value shows its source.

## Who it is for

People who need a list from the web and today either ask a developer for a scraper or copy-paste into a spreadsheet.

- Hiring: job openings
- Sales: leads
- Partnerships: sponsors
- Research: market data

## The job

"When I need a list of something from the web, I want to describe it once and get a spreadsheet
I can trust and keep up to date, without writing or maintaining scrapers."

## Principles (every UI decision is checked against these)

1. Show the plan before acting. Nothing runs until the user approves it.
2. Every value has a receipt: source URL, capture time, and the quoted text it came from.
3. Missing beats invented. A value that was not found stays empty and is marked "not found".
4. Permitted sources only. Skipped sources are listed with the reason.
5. Plain language first; technical detail one click away.

## Core objects (shared vocabulary and the API contract)

The TypeScript version of these lives in `src/domain/types.ts`.

| Object  | Holds |
|---|---|
| Request | The user's sentence and the parsed intent |
| Plan    | Columns (name, type, required), filters, sources, interpretations of unclear words, row limit |
| Run     | One execution of a plan: status, progress per source, event log |
| Dataset | Versioned result of a run: rows and the cleaning report |
| Cell    | value, sourceUrl, capturedAt, quote, confidence (high/medium/low), status (found/not found/conflict) |
| Source  | Domain, permission (allowed / disallowed by robots.txt / needs login / rate-limited), method, health |
| Monitor | A plan plus a schedule. Each run makes a new dataset version and a change list |

## The flow

| Step   | User does | AWDAX shows | PS-01 goal |
|---|---|---|---|
| Ask    | Types a request, or picks an example | Suggestions while typing | Understand plain-English requests |
| Plan   | Edits columns, filters and sources, then approves | Proposed columns and types, filters, sources with permission status, how unclear words were read | Design the workflow |
| Run    | Watches, pauses, cancels, retries a source | One lane per source: queued, fetching, extracting, done or skipped with reason; rows found; activity log | Collect from several permitted sources; monitor and manage |
| Review | Checks merges and conflicts, overrides if needed | Raw rows to unique rows, merged groups, rows that failed checks and why, values that disagree across sources | Clean, validate, remove duplicates |
| Use    | Searches, filters, exports, saves as a monitor | Table with a source drawer per cell, auto charts, CSV/JSON export, change list for monitors | Traceable data, dashboard, history, export |

## Web app screens

As built on 2026-09-28 against the real backend. `docs/APP.md` has the detail; the original list is kept below it.

1. New chat: one prompt box (text, voice, or a CSV/Excel/JSON file), a shortcut strip, "See what AWDAX can do" cards
2. Chat: the request, the backend's replies, the live run (phase and pipeline steps), then the dashboard and questions
3. Dashboard (Power BI style): suggested charts plus build-your-own, resizable and movable tiles, slicers,
   click-to-filter, every row in a grid, and an exact precision note under each chart
4. Questions: follow-up chips and the same prompt box, answered exactly from the rows (never re-scraped)
5. Projects report: every web request and uploaded file with status, rows, search, filter buttons and quick queries
6. Ask database: question any project with rows; the query builder pins results to its dashboard
7. Export: SQL (PostgreSQL, MySQL, SQLite, SQL Server), JSON, JSON Lines, CSV, TSV, Excel, XML, Markdown

Not built, because the backend doesn't support them yet:
- plan review before running;
- per-cell receipts: each row keeps its `source` and `source_url`, but values don't carry a quote or capture time;
- robots.txt checks;
- choosing between sources that disagree: both rows are kept, one per source;
- the cleaning report;
- dataset versions and monitors with change lists: web requests refresh every 5 minutes instead, merging changed
  and new rows.

The landing FAQ (updated 2026-09-28) only claims what is built. The original plan was:
Home · Plan review · Run · Dataset (Table, Charts, Cleaning report, Sources) · History · Monitors · Guided tour.

## Collection methods (the "method" shown on each value)

Cheapest first; the UI shows which method produced each value. Each method has its own color.

1. Structured data: JSON-LD, OpenGraph, RSS, sitemaps
2. Page content: main-text extraction from plain HTML
3. Rendered page: headless browser, for pages built by JavaScript
4. AI reading: model extraction against the plan's columns, validated before it is accepted

## Failure states (designed up front)

| Situation | What the user sees |
|---|---|
| Source disallowed by robots.txt | Skipped, reason shown, alternative sources suggested |
| Blocked or CAPTCHA | Skipped and logged. No bypass attempt |
| Zero results | Why (for example, filters too tight) and a one-click way to loosen them |
| Unclear request | The plan shows how it was read, with alternatives. It asks a question only if no plan can be made |
| Some sources fail | The dataset is usable with what was found; failed sources are listed |
| Sources disagree on a value | Both values shown; one chosen by rule (most recent, then most sources); user can override |

## Charts rule

One sentence under each chart says why it was chosen. The app suggests 4 to start (owner decision, 2026-09-27:
the dashboard is Power BI style, so people add, change, resize and remove charts freely; this replaces "maximum 4").
Every chart states what it counted, how many rows it used and which cells it left out and why.

- Date column: line chart, count over time
- Ordered category column (tiers, sizes; up to 6 levels): donut in one hue, dark to light
- Other category column: bar chart, top 6 plus "Other", one color
- Number column: histogram
- Location column: bar chart by region
- A column with only one group gets no chart. Charts never use a rainbow palette, because four hues already mean collection methods.
- The code for this rule is `src/domain/charts.ts`.

## What AWDAX does not do (the site says this plainly)

- No login bypass, no CAPTCHA solving, no collecting from disallowed paths
- No invented values
- Not a full BI tool: the dashboard covers the data AWDAX collected or you uploaded; for joins across sources and
  modelling, export to SQL, Excel or Power BI (CSV).

## Sample data (fixtures until a real run replaces them)

All sample entities are fictional, and every place they appear is labeled "sample run".
Real companies are never shown with invented numbers.

| Use case | Request | Columns |
|---|---|---|
| Jobs     | Frontend developer internships in Bengaluru posted in the last 14 days | title, company, location, stipend, posted_at, apply_url |
| Leads    | Seed-stage fintech startups in India funded in 2026, with founders and amount | company, founders, amount_usd, round_date, investors, website |
| Sponsors | Companies that sponsored student hackathons in India in 2026 | company, event, tier, date, contact_page |
| Market   | 5G smartphones under ₹20,000 from Indian retailers | model, brand, price_inr, retailer, rating, in_stock |

## Landing page story

Hero (a live sample run) → How it works → You approve the plan → Every value has a source →
Clean by default → Dashboards and monitors → Permitted sources only → Video tour → FAQ and final call-to-action.

Voice: calm and specific. Banned words: revolutionary, seamless, unleash, supercharge, game-changing.
No team names, no hackathon references, no logo wall, no testimonials.

## Questions for the backend team (the frontend is not blocked by any of them)

1. Run events: server-sent events or WebSocket? The frontend assumes server-sent events behind one adapter.
2. Does extraction return the quoted text for each value? Principle 2 depends on it.
3. Is robots.txt checking implemented? Landing section 6 depends on it.
4. Scheduled re-runs for monitors by Oct 11? If not, the site marks monitors as "coming soon".
