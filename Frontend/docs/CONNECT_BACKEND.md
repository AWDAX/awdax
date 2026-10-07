# Connecting the site to the backend

The site and the backend are served from one domain, so the browser calls its own `/api/*` (no CORS, no separate proxy service). In production a
Caddy container does the routing and HTTPS, and the backend verifies the Supabase sign-in token itself. The full guide is **docs/DEPLOY.md** (repository
root); the settings are in docs/CONFIGURATION.md.

## Locally

`npm run dev` forwards `/api`, `/health` and `/ready` to `http://127.0.0.1:8000` (`vite.config.ts`). If the backend listens elsewhere, put
`AWDAX_API=http://127.0.0.1:<port>` in `Frontend/.env.local` and restart. Sign-in, or the no-sign-in development mode, is explained in LOCAL_DEV.md.

## What the site sends

- `Authorization: Bearer <Supabase access token>` on every request, and the same token in an `awdax_token` cookie scoped to `/api`, because server-sent
  events and WebSockets cannot send headers.
- Nothing is sent when the user is signed out; the app shows the sign-in page instead of calling the API.

## Messages you may see

| Message | Meaning |
|---|---|
| "Can't reach the AWDAX server" | The backend is not running, or `/api` is not routed to it. |
| "The AWDAX server isn't connected to this site yet" | `/api` is answered by the static site, not the backend (a missing proxy rule). |
| "Your sign-in could not be verified" (401) | The token is missing or invalid, or `SUPABASE_URL` is missing on the backend. |
