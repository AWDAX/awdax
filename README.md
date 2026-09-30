# AWDAX

**Ask for data. See where it came from. Explore it your way.**

AWDAX turns a plain-language research request into a dataset you can inspect, chart, question, and export. It shows the sources it finds while the work is happening, so you can follow a request from discovery through to the rows in your report. You can also start with a data file you already have.

## What you can do

- **Research the web with a request.** Describe the information you need, such as electric vehicles in India with prices and range. AWDAX searches for relevant sites, inspects pages, extracts rows, and combines the results into a table. It also has a dedicated path for Indian eGazette requests.
- **Watch discovery live.** See sources appear as they are found and inspected, follow page-reading and row-collection progress, and open the Sources view to review where the collected data came from.
- **Inspect the data.** The Data view shows the collected rows and their source URLs. Where scoring is available, it also shows quality information and lets you include partial rows.
- **Let the data suggest charts.** Dates can become timelines, categories can become comparisons or shares, and numeric fields get their own scales. The Graphs view chooses a useful chart by default; you can switch between line, bar, column, area, pie, donut, scatter, number card, and table views, or edit the fields and aggregation yourself.
- **Ask follow-up questions.** Ask for totals, averages, rankings, and comparisons using the rows already collected. These questions are answered from the current table and do not start another scrape.
- **Keep a request active.** Live chats can continue checking for new rows. You can pause or resume tracking and turn on new-row alerts.
- **Take the result elsewhere.** Export all rows, filtered rows, a chart's numbers, or an answer as CSV, Excel, JSON, SQL, TSV, XML, Markdown, or JSON Lines.

## A typical workflow

1. Start a chat with a request such as **“Electric vehicles in India with prices and range.”**
2. Watch AWDAX discover and inspect sources, then collect rows.
3. Review the **Report**, **Data**, **Graphs**, and **Sources** views.
4. Change a chart if another view tells the story better, or ask **“What is the average price by brand?”**
5. Export the data or leave the chat tracking for new rows.

Results depend on the pages available for a particular request. AWDAX keeps missing or unreadable values visible as gaps instead of inventing numbers.

## Bring your own data

Upload a CSV, TSV, JSON, or `.xlsx` file to use the same dashboard, graphs, questions, and exports without scraping. Uploaded files stay in this browser on this device. The sample run in the app is a quick way to explore the experience before starting a web request.

## Run locally

This folder contains the Flask backend (`app.py`) and the React app (`Frontend/`). Use two PowerShell terminals.

**Backend** — from this folder:

```powershell
if (-not (Test-Path .venv)) { py -3.11 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe app.py
```

Set `GEMINI_API_KEY` in the backend `.env` before starting a real web request. Flask runs at `http://127.0.0.1:8000` by default.

**Frontend** — in the second terminal:

```powershell
cd Frontend
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm ci
npm run dev:agent
```

Add your Supabase `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` to `Frontend/.env.local`, then open `http://localhost:5174/`. The Supabase project must allow `http://localhost:5174/auth/callback` as a redirect URL. The frontend sends local API requests to port 8000; `npm run dev` uses port 5173 instead.

For more setup detail, see [local development](LOCAL_DEV.md) and the [frontend README](Frontend/README.md).

## If something goes wrong

- **`ECONNREFUSED 127.0.0.1:8000`:** Start the backend and leave its terminal running. Check `http://127.0.0.1:8000/health`.
- **An error remains after a code change:** Stop and restart Flask. Its automatic reloader is disabled; an old failed message also remains in chat history until you submit a new request.
- **Sign-in fails:** Check the two Supabase values and the callback URL for the port you are using.
- **Discovery cannot reach Gemini:** Check `GEMINI_API_KEY` in the backend `.env` and restart Flask.

The startup messages about `google.generativeai` and `fitz` are deprecation warnings; they do not stop the local server from starting.

## Developer notes and safety

The backend API and legacy scraper interface live in `app.py` and `awdax_api/`; frontend code lives in `Frontend/`. Backend tests are in `tests/test_awdax_api/`, and frontend commands are listed in [Frontend/README.md](Frontend/README.md).

Keep the Flask backend local. It does not yet enforce per-user ownership or authenticate direct API requests, so it should not be exposed through a public tunnel. Keep API keys in the backend `.env`, never in a `VITE_` variable. See the [deployment notes](../DEPLOY.md) before planning a hosted setup.
