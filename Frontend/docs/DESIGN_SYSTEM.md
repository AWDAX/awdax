# AWDAX design system — "The web, highlighted"

The values live in `src/styles/tokens.css`. This file says what they mean and when to use them.
Components never use a raw hex; they use these token names through Tailwind (`bg-signal`,
`text-m-content-line`, `border-ink`) or the `mark-*` utilities in `src/index.css`.

## Direction

- **Feeling:** bold and exact. A research desk, not a SaaS dashboard.
- **Reference class:** data journalism × developer tool.
- **References** (Awwwards 2026 winners; no code or assets copied):
  AI in Design Report (charts: ink on paper, one accent wash) ·
  Why Zero (color energy: saturated fills used sparingly) ·
  Squarespace Foundations (ink-and-paper rules: heavy black rules, true white ground).
- **The one memorable thing:** the hero shows the page AWDAX is reading. Values get highlighted in
  their method's color, then a line traces each highlight to the table cell it became.

## Paper and ink

| Token | Value | Use |
|---|---|---|
| `canvas`, `surface` | `#ffffff` | Page and panels: true white paper |
| `sunken` | `#f4f4f1` | Recessed wells, chart track |
| `line` | `#e3e3de` | Hairlines inside a panel (table rows) |
| `line-strong` | `#b9b9b2` | Stronger dividers, hover guides |
| `ink` | `#0b0b0c` | Text, 2px borders and rules, primary shapes |
| `ink-2` | `#3d3d3a` | Secondary text |
| `ink-3` | `#6b6b66` | Tertiary text, captions (4.5:1 on white) |
| `on-ink` | `#ffffff` | Text on an ink fill |

## Highlighters: color has exactly one meaning each

Color appears **only** as highlighter fills. Text on a highlighter is always ink.
The `*-line` variants are darker versions for strokes, icons and text on white, where the fill
color would be too light to read.

| Meaning | Fill token | Line token | Where |
|---|---|---|---|
| AWDAX: the promise, primary actions, "just found" | `signal` `#ffe92e` (`signal-hover` `#ffe100`, `signal-soft` `#fff6a8`) | — (use `ink`) | Primary button, headline highlight, current step, row just arrived |
| Structured data (JSON-LD, OpenGraph, RSS) | `m-structured` `#7dfc8f` | `m-structured-line` `#0b8a3a` | Values read from structured data |
| Page content (plain HTML text) | `m-content` `#8fd0ff` | `m-content-line` `#0f62d1` | Values read from page text |
| Rendered page (headless browser) | `m-rendered` `#ffbd6b` | `m-rendered-line` `#b35400` | Values from JavaScript-built pages |
| AI reading (model extraction, validated) | `m-ai` `#ff9ce0` | `m-ai-line` `#c0168c` | Values read by the model |
| Skipped / rejected (red pen) | `blocked` `#e0251b` | — | `line-through decoration-blocked decoration-2`, ban icon |

`on-signal` is ink. There are no `*-soft` method tokens: a lighter tint would be a second meaning.

## The highlighter utility

```html
<span class="mark mark-on mark-content">Stipend: ₹20,000 /month</span>
```

- Always `mark` + exactly one of `mark-on` / `mark-off` + exactly one color
  (`mark-yellow`, `mark-structured`, `mark-content`, `mark-rendered`, `mark-ai`).
- Switching `mark-off` → `mark-on` sweeps the fill in from the left (480 ms, ease-out-expo).
- Hover pattern: `mark mark-off mark-yellow group-hover:mark-on` (or `hover:mark-on`).
- In React, use `<Mark ink="content" on delay={120}>` from `src/ui/Mark.tsx`.
  `useArrived()` from `src/ui/useArrived.ts` returns false on first paint and true after two frames,
  so a mark that should sweep on mount can start off.

## Type

| Token | Font | Use |
|---|---|---|
| `font-display`, `font-sans` | Mona Sans (variable width 75–125, weight 200–900) | Everything textual |
| `font-mono` | Geist Mono 400/500 | Data, URLs, step numbers, code captions |
| `font-wide` utility | `font-stretch: 125%` | Headlines and the wordmark, at weight 800 |

`text-display` = `clamp(2.5rem, 6vw, 5.5rem)`, line-height 0.94, letter-spacing −0.03em (hero).
`text-section` = `clamp(2rem, 3.4vw, 3.25rem)`, line-height 1.02 (section headlines: two lines in eight columns).
Body text stays at 100% width. No uppercase micro labels.

## Shape

- `radius-control` 4px (buttons, tags, fields), `radius-panel` 6px (pages, drawers).
- Borders and rules are 2px ink. Hairlines (`line`) only inside a panel, between rows.
- No shadows (`shadow-float` is `none`), no pills, no gradients.

## Buttons (`src/ui/buttonClass.ts`)

- Primary: 2px ink border, yellow fill, ink text; hover inverts to ink fill, yellow text.
- Secondary: 2px ink border on white. Ghost: transparent border.
- All: `active:scale-97`, ink focus ring offset 3px.

## Charts

Ink on paper. One series is ink (`series`), with a yellow wash under lines (`series-wash`).
Ordered levels use the grey ramp `ramp-1..5` (light to dark); "Other" is `other`.
Never a categorical rainbow inside one chart: the method hues already have meanings.

The user can give a tile one colour of its own (tile menu → Colour; owner decision, 2026-09-28): `chart-ink`
(default), `chart-blue`, `chart-teal`, `chart-green`, `chart-orange`, `chart-purple`, `chart-pink`. The tile then
re-points `series`, `series-wash` and `ramp-1..5` at that colour (`src/app/dashboard/chartColor.ts`), so a donut
becomes shades of one hue. Cross-filter picks stay signal yellow. No signal-yellow or red option: yellow means
"picked" and red means "skipped".

## Motion: three verbs, nothing else animates

| Verb | Meaning | How |
|---|---|---|
| **Highlight** | found | `mark-off` → `mark-on` sweep |
| **Trace** | came from here | SVG path drawn by `pathLength` from a highlight to its cell (`TraceLayer`) |
| **Strike** | skipped | red-pen `line-through` |

Supporting moves (a row arriving, a page swapping, a chart filling in) stay quiet.

### Timing: slow and soft on purpose

| What | Duration | Curve |
|---|---|---|
| Highlight sweep (`mark`) | 900 ms | `ease-draw` (0.65, 0, 0.35, 1): a hand drawing a stroke |
| Strike (`strike`) | 800 ms | `ease-draw` |
| Trace line | 1 s, 160 ms between lines | `EASE_DRAW` in `src/ui/motion.ts` |
| How-it-works band | 900 ms | `ease-draw` |
| Arrivals, charts, row scroll, page swap | 450–700 ms | `ease-soft` (0.33, 1, 0.68, 1) |
| Buttons, nav | 300 ms | `ease-soft` |

Staggers are 130–220 ms. Scrolling is Lenis (lerp 0.075); in-page links glide 1.4 s and stop below the
nav through each section's `scroll-mt-16`.

Every animation has a reduced-motion fallback: the final state, drawn, with nothing moving. Lenis
turns its smoothing off by itself for reduced motion.
