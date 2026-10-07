# AWDAX — frontend

AWDAX turns a plain-English data request into a clean dataset where every value shows its source.
This repo is the landing page (and, next, the web app).

## Run it

```bash
npm install
npm run dev      # http://localhost:5173
npm run build    # type-check and production build into dist/
npm run lint
```

## Environment

Sign-in needs two public values in `.env.local` (git-ignored; `*.local`):

```
VITE_SUPABASE_URL=https://<project-ref>.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
```

Both are safe in the browser. Set the same two in the hosting provider before deploying. Never put a
Supabase secret or service_role key in this repo or in any `VITE_` variable: Vite ships those to the browser.

### Local backend (AwdaxP)

The signed-in app talks to [AwdaxP](../awdaxp/) for chats, live runs and dashboards.

1. In `awdaxp/`: configure `.env` (browser binary, API keys), then `python app.py` on port **8000**.
2. In this folder: `npm run dev` on port **5173**. Vite proxies `/api`, `/health`, and `/ready` to `http://127.0.0.1:8000`.

Optional in `.env.local`:

```
AWDAX_API=http://127.0.0.1:8000
```

For production the site and the backend share one domain behind a reverse proxy; see `docs/CONNECT_BACKEND.md`.

## Stack

React 19 · TypeScript · Vite 8 · Tailwind CSS v4 · Motion · React Router · Lenis · Supabase Auth (Google).
The Supabase client loads only on `/login`, `/auth/callback` and `/app`, never on the landing page.
Charts are hand-built SVG (`src/product/chart/`); there is no chart library.

## Where things are

| Path | What |
|---|---|
| `src/landing/` | The landing page: hero, sections, nav, footer |
| `src/product/` | Product components shared with the app: plan, rows, receipts, charts |
| `src/domain/` | Types (the backend contract), formatting, chart rules, sample data |
| `src/ui/` | Primitives: buttons, highlighter (`Mark`), red pen (`Strike`), smooth scroll |
| `src/styles/tokens.css` | Every color, size and easing |

## Read before changing anything

- `AGENTS.md`: rules, commands and the design direction
- `docs/PRODUCT.md`: what AWDAX does and the principles every screen follows
- `docs/DESIGN_SYSTEM.md`: tokens, the highlighter colors and what each one means, motion timing
- `docs/LANDING.md`: each landing section, its reference and its components

All sample data on the site is fictional, on reserved `.example` domains, and labeled "sample run".
Third-party fonts and libraries are listed in `CREDITS.md`.
