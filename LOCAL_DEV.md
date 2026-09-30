# Local development: Flask backend + React Frontend

## Backend (scraper2.0)

```bash
cd /path/to/scraper2.0
pip install -r requirements.txt
PORT=8000 python3 app.py
```

- Legacy UI: http://127.0.0.1:8000/ (`index.html`, `/api/sessions/*`)
- Awdax compat API (React): `/health`, `/api/instances/*`, WebSocket `/api/instances/:id/live/ws`

Default port **8000** matches the Frontend Vite proxy (`AWDAX_API=http://127.0.0.1:8000`).

## Frontend

```bash
cd Frontend
cp .env.example .env.local   # optional; default proxy target is 8000
npm install
npm run dev
```

Open http://localhost:5173/app — new chat calls `POST /api/instances/:id/messages` which runs the full scraper pipeline in the background.

## Environment

- `GEMINI_API_KEY` — required for real discovery/scrape
- `SCRAPE_MAX_PAGES`, `REGULATORY_SCRAPE_MAX_PAGES` — listing depth
- `PORT` — Flask listen port (use 8000 for Vite without extra config)
