# Architecture

AWDAX is a Flask backend (threads, SQLite, headless Chrome) and a React frontend. This is how a request becomes a dataset, and where each part lives.

```
browser ──/api/*──▶ Caddy ──▶ gunicorn (1 worker, many threads) ──▶ Flask app (app.py, awdax_api/)
   ▲  SSE / WebSocket                                                   │ one run thread per chat
   └────────────── live_bridge ◀── scraper events ◀── run pipeline ◀────┘
Claude ──/api/mcp──▶ (same API) ──▶ mcp_server (python -m mcp_server, tools call the REST API with the caller's key)
```

## One request, step by step

1. **Message** (`POST /api/instances/<id>/messages`, `awdax_api/routes.py`). The caller is identified first (`auth_helper.py`), the chat is loaded
   *as that user* (`ui_sessions.py` refuses a missing user id), and the message is saved. `orchestrator.submit_run` starts the run, or puts it in the
   waiting line when the server is at its run limit (`awdax_api/run_registry.py`: `AWDAX_MAX_RUNS`, `AWDAX_MAX_RUNS_PER_USER`, `AWDAX_MAX_QUEUE`).
2. **Intent** (`reasoning.py`). The model turns the text into a `ScrapeIntent`: topic, place, fields, constraints and a pipeline. Rule-based
   corrections follow (`regulatory_strategy.py`, `places_strategy.py`).
3. **Route.**
   - `places`: Google Maps (`places_pipeline.py`, `places_search.py`, `places_sites.py`). Named places are geocoded and tiled; with no place, rings
     widen around the user. Calls are metered and capped. Rows are scored as leads; each business's own site can be read for contacts.
   - `regulatory_feed`: the eGazette pipeline (`RegulatoryFeed.py`, `gazette_*.py`), a dedicated scraper for that one portal.
   - `universal`: everything else, below.
4. **Research** (`web_research.py`, `gemini_search.py`). Gemini searches Google through its REST `google_search` tool and returns a ranked list of
   the best websites (deep links to the listing, not home pages). Stored with the chat and shown in the Sources view.
5. **Discovery** (`inspector.discover_inspected_from_queries`). Order: the ranked sites (best first; a dead link falls back to a page Google cited,
   then to its parent section; a rejected front page is followed to the links a person would click), the curated anchors for known topics
   (`listing_sources.py`), then generated searches (`query_generation.py`, `source_search.py`). Searches stop after `DISCOVERY_ENOUGH_SOURCES`
   accepted sources or `DISCOVERY_MAX_SECONDS`.
6. **Inspection** (`inspector.inspect_source`). Every link first gets one plain request (`url_access.py`; failures are kept per run as the
   failed-links dataset). Then **one** browser visit (`browser.py`) captures the rendered page, its tables, its links, its accessibility tree and
   the JSON it loaded. The model judges whether the page lists the requested records; a page that only talks about them is rejected.
7. **Scrape** (`scraper.py`, `_listing_rows`). Per source, the best route it offers:
   1. data files the page offers (`dataset_files.py`): downloaded to a temp file, read, filtered, stored, then deleted;
   2. the data feed behind a JavaScript table (`data_feed.py`): paged with plain requests, the period sent to the feed when it takes dates;
   3. the accessibility tree (`ax_reader.py`): for pages built by JavaScript; the pager ("Next", "Go to next page", "Load more") is pressed;
   4. the page's HTML digest (`gemini_scrape.py`, `listing_extract.py`): plain pages, tables read as rows, long tables in chunks, "Next" links followed.
   Rows pass `row_limits.py` (the request's period) and `row_quality.py`, are stored in order on one connection, and merged across sources
   (`table_merge.py`). Sources are fetched in parallel (`SCRAPE_WORKERS`); a paused or deleted chat stops the pass at its next source or row.
8. **Live view** (`awdax_api/live_bridge.py`). Scraper events become SSE/WebSocket messages, batched so the table refreshes about every two seconds.
9. **Dataset** (`awdax_api/dataset_export.py`). The merged table, with the source of every row; the Sources, Graphs and Dashboard endpoints read it.

## Questions about the data (`ask_data.py`, `ask_fastpath.py`, `query_engine.py`, `ask_sandbox.py`)

A plain question ("average price by brand") is answered by rules; otherwise the model writes a *plan* (one group-by, one aggregate, filters) that the
engine runs with exact decimals, or a short calculation that runs in a sandbox with no file or network access. The browser engine
(`Frontend/src/analytics/`) and the server engine are tested against the same golden fixture (`tests/fixtures/ask_math.json`).

## Identity and isolation

Strict by default: a request must carry a Supabase token the backend verifies itself (ES256 via `SUPABASE_URL`, or HS256 via `SUPABASE_JWT_SECRET`)
or an API key (`api_keys.py`, `awx_...`, hashed with `API_KEY_PEPPER`, read or write scope, rate-limited). Every chat belongs to one user; every
route loads it with that user's id, and another user's chat answers 404. Live events are routed by chat id, never "to whoever is running".
`AWDAX_AUTH_MODE=dev` (local only) trusts unverified identities and logs a warning.

## Storage

One SQLite file (`SQLITE_PATH`, default `regulatory.sqlite`): chats (`ui_sessions`), scraped rows, API keys, Maps usage and the geocode cache,
failed links, the eGazette feed. A chat is saved by writing only the fields a writer changed (`update_session_fields`), so a late live event can
never overwrite a finished run. Data files and downloads live in the temp folder only until their rows are stored.

## Where things are

| Area | Files |
|---|---|
| API, auth, runs | `app.py`, `awdax_api/` (`routes`, `orchestrator`, `run_registry`, `pipeline_runner`, `live_bridge`, `key_routes`, `ask_routes`, `openapi`, `mcp_proxy`), `auth_helper.py`, `api_keys.py`, `ui_sessions.py` |
| Models | `llm_client.py` (NVIDIA first, Gemini with retries and fallback), `reasoning.py`, `gemini_search.py` |
| Finding sources | `web_research.py`, `discovery.py`, `source_search.py`, `query_generation.py`, `listing_sources.py`, `inspector.py`, `url_access.py`, `url_guard.py` |
| Reading pages | `browser.py`, `ax_reader.py`, `data_feed.py`, `dataset_files.py`, `listing_extract.py`, `gemini_scrape.py`, `plan_scraper.py`, `listing_scrape.py`, `scraper.py` |
| Rows | `row_limits.py`, `row_quality.py`, `table_merge.py`, `table_schema.py`, `column_kinds.py` |
| Maps | `places_strategy.py`, `places_pipeline.py`, `places_search.py`, `places_sites.py` |
| eGazette | `regulatory_strategy.py`, `RegulatoryFeed.py`, `gazette_scraper.py`, `gazette_pdf.py`, `gazette_summary.py` |
| Questions | `ask_data.py`, `ask_fastpath.py`, `query_engine.py`, `ask_sandbox.py` |
| MCP | `mcp_server/` |
| Tools | `scripts/sessions_admin.py` (list, assign or purge chats that belong to no user) |
| Website | `Frontend/` (React, Vite, TypeScript; `src/api` talks to the backend, `src/app` is the product, `src/analytics` the browser-side maths) |

## Known limits

- One gunicorn worker: run state, the waiting line and live loops are in memory. Scaling beyond one server needs those moved out (a shared queue and
  worker processes).
- Each browser step opens its own Chrome; there is no shared browser pool, so memory is the real limit on concurrent runs.
- The accessibility-tree reader and the feed reader are tested on a handful of sites (docs/AX_TREE_EXPERIMENT.md); iframes, shadow DOM, infinite
  scroll and bot-blocking sites are not covered.
