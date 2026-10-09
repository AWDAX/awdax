# Configuration

Every setting is an environment variable, read from `.env` in the repository root (git-ignored; `app.py` loads it, Docker Compose passes it in).
**`.env.example` lists every setting with its default and a one-line explanation**; this page covers what you have to decide and why.

## What you must set

| Setting | Why |
|---|---|
| `GEMINI_API_KEY` | The model plans requests, ranks websites and reads pages. Without it nothing can run. Get a key at https://aistudio.google.com/apikey. |
| `SUPABASE_URL` | Every request must prove who sent it. The backend checks the Supabase sign-in token against `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. Without it, sign-in fails with "Your sign-in could not be verified". Only Google sign-ins are accepted: turn off the Email and Anonymous providers in Supabase too. |
| `API_KEY_PEPPER` | Secret mixed into the hash of every API key. Generate once (`python -c "import secrets; print(secrets.token_urlsafe(48))"`) and never change it: a new value invalidates every key. |
| `GOOGLE_MAPS_API_KEY` | Only for local-business and "leads" requests. Enable *Places API (New)* (required) and *Geocoding API* and restrict the key to them. Without it those requests use ordinary web discovery. |

The website needs two public values at build time: `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` (`Frontend/.env.local` locally; in the root
`.env` for the Docker build). They are not secrets.

## Sign-in modes

| Mode | When | How |
|---|---|---|
| Strict (default) | Always in production | Supabase token (verified), or an `awx_` API key. Anything else gets 401. |
| `AWDAX_AUTH_MODE=dev` | Your machine only, with `npm run dev:agent` | Trusts the `X-User-Id` header and unverified tokens. The backend logs a warning. Never set it on a server. |
| `PROXY_SHARED_SECRET` | Only behind your own authenticating proxy | The backend accepts `X-User-Id` only with a matching `X-Proxy-Secret`. Leave empty otherwise. |

In the Supabase dashboard add your site (for example `https://awdax.synapical.com`) to Authentication → URL configuration (Site URL and Redirect URLs).

## Capacity: runs, browsers and memory

A run opens Chrome windows while it inspects pages (`DISCOVERY_INSPECT_WORKERS`, default 3) and while it scrapes (`SCRAPE_WORKERS`, default 3); a
Chrome window needs roughly 300-500 MB. `AWDAX_MAX_RUNS` (10) and `AWDAX_MAX_RUNS_PER_USER` (5) say how many runs may be active; the rest wait in a line
(`AWDAX_MAX_QUEUE`, 20) and start by themselves when a slot frees. Size them to the machine, not to the number of users: on a 4 GB server
use `AWDAX_MAX_RUNS=3` or lower the two worker settings.

## Cost controls

- **Gemini**: one request costs a handful of model calls; `DISCOVERY_ENOUGH_SOURCES` and `DISCOVERY_MAX_SECONDS` bound the searching, and
  `GEMINI_ATTEMPTS` bounds retries when Gemini is busy.
- **Google Maps**: the defaults keep a run inside the free tier (`PLACES_MONTHLY_CALL_CAP=1000`, `PLACES_MAX_CALLS_PER_USER_DAY=200`,
  `PLACES_MAX_CALLS_PER_RUN=40`). Raise them only on purpose. Google's terms restrict how long Places content may be kept:
  `PLACES_RETENTION_DAYS` deletes Maps data older than that many days at start-up (0 = keep).
- **Downloads**: `DATASET_MAX_MB` (50) and `DATASET_MAX_ROWS` (5000) cap a data file; `FEED_MAX_ROWS` (1000) caps a data feed.

## Where data lives

`SQLITE_PATH` (default `regulatory.sqlite` beside the code; `/data/regulatory.sqlite` in Docker, on a volume). It holds the chats, rows, API keys and usage
counters: back it up (docs/DEPLOY.md). Data files and downloads sit in the temp folder only until their rows are stored.

## Browser

`CHROME_BIN` and `CHROMEDRIVER_PATH` name the browser and its driver when they are not on the default path (the Docker image sets both). Chrome starts
with `--no-sandbox` and `--disable-dev-shm-usage` everywhere (`browser.py`), which servers and containers need.
