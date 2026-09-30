# AWDAX landing page — sections

Order: Hero → How it works → You approve the plan → Every value has a source → Clean by default →
Dashboards and monitors → Permitted sources only → (Video tour) → FAQ → Final call to action → Footer.

Every section sits in `Section` (`src/landing/SectionHead.tsx`): on desktop at least one screen tall
below the nav, content centred, sized to fit a 1536×864 laptop in one view (checked at 1440×900 and
1920×1080 too). Headings use the split `SectionHead`: headline left, lede right.

Every section follows `docs/DESIGN_SYSTEM.md`: ink on white, color only as highlighter fills with one
meaning each, Mona Sans (wide 800 headlines), 2px ink rules, 4px radius, no shadows. Motion uses only
the three verbs: **highlight** (found), **trace** (came from here), **strike** (skipped / rejected).

References: the three marked ★ are the Awwwards 2026 winners named in the redesign brief. The others are
pattern references (not award claims); swap in an award link if one fits better.

Sample data comes from `src/domain/fixtures/*`: fictional, on `.example` domains, labeled "sample run".

---

## 0. Hero (built)

`sections/Hero.tsx`, `hero/*`. The source page being read; highlights traced to the cells they became.

## 1. How it works — `#how`

- **Reference:** ★ Squarespace Foundations (heavy ink rules, a table of contents as the layout);
  data-journalism scrollytelling (a pinned graphic that changes step by step as you scroll).
- **Layout:** five full-width rows, Ask → Plan → Run → Review → Use, pinned while the section scrolls
  (lg and up). The current step gets a full-width yellow band (highlight verb) and shows a small
  visual built from the Internships sample. Below lg: a plain list, each row highlighted as it enters.
- **Components:** `sections/HowItWorks.tsx`, `how/steps.tsx` (copy + visuals), `SectionHead`, `Mark`, `Strike`.
- **Why yellow for every step:** yellow means AWDAX; a different hue per step would give the method
  colors a second meaning.

## 2. You approve the plan

- **Reference:** `terraform plan` → `apply`: a proposed change is reviewed before anything runs.
- **Layout:** heading and three short points left; an editable plan right (Internships sample).
  Optional columns can be dropped (struck, red pen); each unclear phrase offers its other readings
  (the chosen one highlighted); skipped sources are struck with the reason; "Approve plan" locks it.
- **Components:** `sections/ApprovePlan.tsx`, `product/PlanEditor.tsx` (reusable by the app's Plan review screen).

## 3. Every value has a source

- **Reference:** data-journalism source notes (every figure cites where it came from); ★ AI in Design
  Report (ink-on-paper tables).
- **Layout:** a table of the Internships sample; click any cell and the receipt beside it shows the value,
  the page URL, capture time, method, confidence and the quoted sentence, highlighted in the method's
  color. Includes a "Not found" cell and a cell where sources disagree.
- **Components:** `sections/Receipts.tsx`, `product/CellReceipt.tsx` (reusable as the app's source drawer).

## 4. Clean by default

- **Reference:** a merge view: many inputs collapse into one output, with a count of what merged.
- **Layout:** raw rows as sources returned them (left) → unique rows (right). Each raw row traces to the
  row it merged into (trace verb); rows that fail checks are struck with the reason (strike verb); the
  value where sources disagree is shown with both answers. Sponsors sample, first rows.
- **Components:** `sections/CleanByDefault.tsx`, `clean/mergeRows.ts`, `hero/TraceLayer.tsx` (reused).

## 5. Dashboards and monitors

- **Reference:** ★ AI in Design Report (charts: ink on paper, one accent wash); bento grid layout.
- **Layout:** bento of five tiles: a sample monitor ("37 new since Monday", labeled sample) with its
  change list; three auto charts (line, donut, bars) from three samples; an export tile showing a real
  cell as JSON with its receipt.
- **Components:** `sections/Dashboards.tsx`, `dashboards/Tiles.tsx`, `product/AutoChart.tsx`.

## 6. Permitted sources only — `#sources`

- **Reference:** copy-editing proof marks (the red pen); ★ Why Zero (saturated color used sparingly).
- **Layout:** a robots.txt excerpt and the URL it rules out; every source from the four samples, allowed
  ones highlighted by method and the rest struck in red pen with the reason; "What AWDAX will not do",
  struck as it scrolls in.
- **Components:** `sections/PermittedSources.tsx`, `Strike`.

## 7. Video tour — deferred

Needs the web app (1–11 Oct). Not on the page until there is a real product to film.

## 8. FAQ — `#faq`, final call to action, footer

- **Reference:** ★ Squarespace Foundations (rules between items, type doing the work).
- **FAQ:** native `<details>`, answers checked against `docs/PRODUCT.md`.
- **Final call to action:** a full-width yellow band with the request field; submitting opens `/app`.
- **Footer:** wordmark, links and the sample-data note. No credits link on the site (owner's call,
  27 Sep); attribution stays in `CREDITS.md` in the repo.
- **Components:** `sections/Faq.tsx`, `sections/FinalCta.tsx`, `Footer.tsx`.
