# AGENTS.md — AWDAX frontend

Read this before touching anything here. It holds what used to live only in chat.
The product is described in `docs/PRODUCT.md`; the visual system in `docs/DESIGN_SYSTEM.md`;
landing sections and their references in `docs/LANDING.md` (written section by section).

## What this is

AWDAX turns a plain-English data request into a clean dataset where every value shows its source.
Flow: Ask → Plan (user approves) → Run → Review (cleaning) → Use (table, charts, export, monitors).
Principles: show the plan before acting; every value has a receipt (source URL, capture time, quoted
text); missing beats invented; permitted sources only (skipped ones shown with the reason).

Deadline: landing page deployable by **30 Sep 2026, 11:59 PM**. Web app screens follow (1–11 Oct).
The owner pushes and deploys. Agents never push, deploy or publish.

## Stack

React 19 · TypeScript 6 · Vite 8 · Tailwind v4 (tokens in `src/styles/tokens.css`) · Motion
(LazyMotion + `m.*`, strict) · React Router 8 · Lenis smooth scroll (`src/ui/SmoothScroll.tsx`). No shadcn, Recharts or TanStack Table: charts are
hand-built SVG in `src/product/chart/*` to keep the landing well under 250 KB gzipped JS.

## Auth

Supabase Auth, Google only, PKCE flow. Project `AWDAX` (ref `allwrzhdjodscxztcewu`). Code in `src/app/auth/`:
`supabase.ts` (the one client), `AuthProvider.tsx` + `authContext.ts` (`useAuth`, `safeNext`), `RequireAuth.tsx`.
Routes (all in the lazy `src/app/AppRoot.tsx`): `/login`, `/auth/callback`, `/app/*` (signed in only).
Env: `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` in `.env.local`. Never a secret key in the frontend.
IDs and where each key lives: the owner's git-ignored `PROJECT_KEYS.md` (never commit it, never print its secrets).

## Commands

```bash
npm run dev        # Vite dev server
npm run build      # tsc -b && vite build
npm run lint       # eslint
node ~/.agents/gates/verify.mjs   # the gate: must print PASS before anything is "done"
```

## Layout

| Path | What |
|---|---|
| `src/domain/` | Types (the backend contract), formatting, chart rules, sample fixtures. Do not change without asking. |
| `src/product/` | Product components shared by the landing and the app: PlanCard, RowStream, SourceChip, AutoChart. |
| `src/landing/hero/` | The hero's sample run: timeline (pure), useTimeline (clock), HeroRun, SourcePage, TraceLayer. |
| `src/landing/sections/` | One file per landing section. |
| `src/ui/` | Primitives: Button, buttonClass, Container, Mark, useArrived, icons. |

## Code style

Single quotes, no semicolons, `.ts`/`.tsx` extensions in imports. Files under 300 lines.
Reuse `src/product/*` before writing a new component. Name the file a pattern was copied from.

## Direction: "The web, highlighted" (decided; do not reopen)

- Feeling: bold and exact. A research desk, not a SaaS dashboard.
- Reference class: data journalism × developer tool.
- The one memorable thing: the hero shows the source page AWDAX is reading. Values are
  highlighted in their method's color, then a line traces each highlight to the table cell it became.
- Color appears only as highlighter fills, each with one meaning everywhere (see DESIGN_SYSTEM.md).
- Type: Mona Sans only (headlines at 125% width, weight 800), Geist Mono for data and URLs.
- Shapes: 4px radius, 2px ink borders and rules, no shadows, no pills.
- Motion has three verbs: highlight (found), trace (came from here), strike (skipped).
  Every animation has a reduced-motion fallback.

## Rules

- No team names, photos or hackathon references on the site. No logo walls, testimonials or
  invented numbers. Sample data is fictional (`.example` domains) and labeled "sample run".
- Every color from `tokens.css`; no raw hex anywhere else in `src`.
  Check: `rg "#[0-9a-fA-F]{3,8}\b" src -g "!styles/tokens.css"` prints nothing.
- No new npm packages without asking the owner first.
- Credit every copied component in `CREDITS.md` (allowed sources: React Bits, Magic UI,
  Aceternity free, Origin UI, Motion Primitives, Cult UI, Skiper UI, with attribution).
- Never commit or push the brief: `/_brief/` and the zip are in `.git/info/exclude`.
- Banned words on the site: revolutionary, seamless, unleash, supercharge, game-changing.
- Before building a landing section, record its award reference and components in `docs/LANDING.md`.

## Done means

`npm run build` passes, `verify.mjs` prints PASS, the hex check prints nothing, and the page was
looked at in a browser at 1440, 1024, 768 and 390 px, plus once with reduced motion, with a clean
console. The owner reviews each landing section in the browser before the next one starts.
