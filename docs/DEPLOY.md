# Deploying AWDAX

One server, one domain. Docker Compose runs three containers: **api** (the backend under gunicorn, with Chromium), **mcp** (Claude's endpoint) and
**web** (Caddy: serves the site, sends `/api/*` to the backend, gets the HTTPS certificate). Written for the Oracle Cloud VM at
`awdax.synapical.com`, but any Linux server with Docker works.

## What you need

- A Linux server (Ubuntu 22.04+ or Oracle Linux), **at least 4 GB RAM** (browsers are the heavy part), ports 80 and 443 open (the Oracle
  security list *and* the server's firewall), and Docker with the Compose plugin (`docker compose version`).
- A domain whose DNS points to the server (`A` record, `AAAA` if it has IPv6).
- A Supabase project with Google sign-in, a Gemini key, optionally a Google Maps key (docs/CONFIGURATION.md).

## First deploy

```bash
git clone https://github.com/AWDAX/awdax /opt/awdax && cd /opt/awdax
cp .env.example .env && nano .env
```

Set in `.env`:

| | |
|---|---|
| `GEMINI_API_KEY`, `SUPABASE_URL`, `API_KEY_PEPPER` | Required (see docs/CONFIGURATION.md). |
| `GOOGLE_MAPS_API_KEY` | For local-business requests. |
| `AWDAX_DOMAIN=awdax.synapical.com` | The site's address: Caddy gets the certificate for it. |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | Public values baked into the site build. |
| Do **not** set `AWDAX_AUTH_MODE` | It must be absent in production (strict sign-in). |

Then:

```bash
docker compose -f deploy/docker-compose.yml --env-file .env up -d --build
docker compose -f deploy/docker-compose.yml --env-file .env ps          # api (healthy), mcp, web all running
curl -s https://awdax.synapical.com/health                              # {"status":"ok"}
```

In the **Supabase dashboard** (Authentication → URL configuration) set the Site URL to `https://awdax.synapical.com` and add it to the
Redirect URLs; if you use your own Google OAuth client, add the domain to its authorised origins. Without this Google sign-in bounces back.

Check it end to end: open the site, sign in with two different Google accounts (two browser profiles), and confirm each sees only its own chats.

## Updating

By hand: `cd /opt/awdax && git pull && docker compose -f deploy/docker-compose.yml --env-file .env up -d --build`.

From GitHub: `.github/workflows/deploy.yml` does the same over SSH when you start it from the Actions tab (or push a tag like `v1.0.0`). Set once, in
Settings → Secrets and variables → Actions: secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` (a key whose public half is in the server
login's `authorized_keys`) and variable `DEPLOY_PATH` (`/opt/awdax`). Create an environment named `production` if you want a manual approval step.
The workflow fails if the backend does not answer `/health` after the restart. Nothing deploys on an ordinary push or pull request.

Roll back: `git checkout <earlier tag or commit>` in `/opt/awdax`, then the same `up -d --build`.

## Connecting Claude (MCP)

Create an API key on the site's *API & MCP* page, then see docs/MCP.md. The endpoint is `https://awdax.synapical.com/api/mcp`.

## Data and backups

Everything is in one SQLite file on the `awdax_data` Docker volume (`/data/regulatory.sqlite`): chats, rows, API keys, usage. Back it up while the
stack runs (SQLite's own backup is safe at any time):

```bash
docker compose -f deploy/docker-compose.yml --env-file .env exec -T api python -c \
  "import sqlite3; s=sqlite3.connect('/data/regulatory.sqlite'); d=sqlite3.connect('/data/backup.sqlite'); s.backup(d); d.close()"
docker cp "$(docker compose -f deploy/docker-compose.yml --env-file .env ps -q api)":/data/backup.sqlite ./awdax-$(date +%F).sqlite
```

Keep `.env` out of the repository (it is git-ignored) and back it up separately; losing `API_KEY_PEPPER` invalidates every API key.

## Operating notes

- **One backend worker, by design.** Run limits, the waiting line and live loops are in the process's memory (docs/ARCHITECTURE.md). Do not raise
  gunicorn's worker count; `GUNICORN_THREADS` (64) is the concurrency knob.
- **Memory.** Each run can hold several Chrome windows. If the server swaps or the api container restarts, lower `AWDAX_MAX_RUNS` (and
  `DISCOVERY_INSPECT_WORKERS` / `SCRAPE_WORKERS`). `docker stats` shows usage.
- **Restarts.** A run that was in progress when the server restarted is marked "interrupted" and can be sent again.
- **Logs.** `docker compose -f deploy/docker-compose.yml --env-file .env logs -f api` (add `web` or `mcp`).
- **Updates of the OS and Docker** are yours; the images are rebuilt from `python:3.12-slim`, `node:24-alpine` and `caddy:2-alpine` on every deploy.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Site loads, every request says "Your sign-in could not be verified" | `SUPABASE_URL` missing or wrong in `.env`; or the clock on the server is far off. |
| Google sign-in returns to the sign-in page | The domain is not in Supabase's redirect URLs. |
| `curl https://domain/health` fails but `docker compose ps` is healthy | DNS not pointing at the server yet, or ports 80/443 closed (security list and firewall). Caddy cannot get a certificate until both are right. |
| Live view arrives in bursts | A proxy in front of Caddy is buffering `/api` (not an issue with this setup); the app falls back to polling within 8 seconds. |
| api container keeps restarting | `docker compose ... logs api`; often out of memory. |
| Runs show "Waiting for a free slot" for long | The run limits are reached; wait, or raise `AWDAX_MAX_RUNS` if the server has memory. |
| Maps requests fall back to web search | `GOOGLE_MAPS_API_KEY` missing, or Places API (New) is not enabled for it. |

## Without Docker

Possible, not packaged: Python 3.12, `pip install -r requirements.txt`, Chrome or Chromium, then
`gunicorn -c deploy/gunicorn.conf.py app:app` and `python -m mcp_server` as services, with `Frontend/dist` (built with the two `VITE_` values) and the
`/api` proxy rules from `deploy/Caddyfile` in whatever web server you use.
