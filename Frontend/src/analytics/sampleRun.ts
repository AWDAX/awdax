import type { DatasetTable } from '../api/types.ts'

/**
 * A sample run in the backend's exact output shapes: the first-pass report text (discovery/format_report.py +
 * extraction/format.py) and the merged master table with `source` / `source_url` on every row. Fictional
 * numbers on .example domains, always labelled "sample run". Used by tests and the sample-run demo.
 */
export const SAMPLE_GOAL = 'Track Indian EV sales every month from 2024 to 2025, by segment'

const SOURCES = [
  { name: 'Vahan EV dashboard', url: 'https://vahan.example/ev/monthly', segments: ['2W', '3W'] },
  { name: 'AutoData India', url: 'https://autodata.example/india/ev-sales', segments: ['4W'] },
]

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const BASE: Record<string, number> = { '2W': 82000, '3W': 51000, '4W': 7400 }
const indian = (n: number) => n.toLocaleString('en-IN')

/** Deterministic, fictional monthly figures with a few gaps ("N/A") like real scrapes have. */
function rows(): string[][] {
  const out: string[][] = []
  for (let i = 0; i < 18; i++) {
    const year = 2024 + Math.floor(i / 12)
    const month = `${MONTHS[i % 12]} ${year}`
    for (const src of SOURCES) {
      for (const seg of src.segments) {
        const season = [0, 2, 9, -4, 1, 3, -2, 0, 5, 14, 11, 6][i % 12]
        const units = Math.round(BASE[seg] * (1 + 0.021 * i) * (1 + season / 100))
        const missing = (seg === '4W' && i === 5) || (seg === '3W' && i === 13)
        const growth = i >= 12 ? `${((0.021 * 12 * 100) + season / 4).toFixed(1)}%` : ''
        out.push([month, seg, missing ? 'N/A' : indian(units), growth || '—', src.name, src.url])
      }
    }
  }
  return out
}

export const sampleTable: DatasetTable = {
  name: 'master',
  source_url: SOURCES[0].url,
  columns: ['month', 'segment', 'units_sold', 'yoy_growth', 'source', 'source_url'],
  rows: rows(),
  row_count: 54,
}

export const sampleReport = `=== AWDAX SOURCE DISCOVERY ===

Goal: Monthly EV registrations in India, 2024–2025, split by vehicle segment
Status: success
Validated: 2 / target 3

Headless browser visited candidate URLs and related links; sources ranked by extractability and authority.

Probable rows (before extract): ~54
  18 months × 3 segments across two sources.

Discovery strategies (reference — URLs come from headless search results):
  • india ev sales monthly 2024 segment wise
  • electric two wheeler registrations month by month
  • ev four wheeler sales india monthly data

VALIDATED SOURCES (2)
---
[1] Vahan EV dashboard
URL: https://vahan.example/ev/monthly
Access: js_rendered
Quality: 9/10 · Authority: 10/10 · Relevance: 9/10
Completeness: full · Format: dashboard
Pages inspected: 3
Likely fields: month, segment, units_sold
Notes: Month selector re-renders a table of registrations by vehicle class.

  Site inspection (headless):
  What we see: A monthly registrations table with a segment filter.
  Best extraction: rendered DOM table (confidence 9/10)
  Expected columns: month, segment, units_sold
  Extraction query:
    table#registrations tbody tr

[2] AutoData India
URL: https://autodata.example/india/ev-sales
Access: http_static
Quality: 8/10 · Authority: 7/10 · Relevance: 9/10
Completeness: partial · Format: html_table
Pages inspected: 2
Likely fields: month, units_sold, yoy_growth
Notes: Four-wheeler EV sales only; one month missing in the source table.

  Site inspection (headless):
  What we see: A static HTML table of monthly passenger EV sales.
  Best extraction: HTML table (confidence 8/10)
  Blockers: June 2024 row is blank on the page
  Extraction query:
    .sales-table tr

REJECTED (4)
---
• EV news roundup
  https://news.example/ev-roundup
  Reason: Article text with rounded figures, no table.

• Dealer association PDF
  https://dealers.example/reports/ev.pdf
  Reason: Scanned PDF; numbers are images.

• Social post
  https://social.example/post/123
  Reason: Unverified figures without a source.

• Paywalled market report
  https://market.example/ev-india
  Reason: Requires login.

=== AWDAX EXTRACTION ===

Extracted 54 rows from 2 sources.

Expected rows (pre-extract): ~54
Estimate: 18 months × 3 segments.
Actual rows extracted: 54

Columns: month, segment, units_sold, yoy_growth, source, source_url
Rationale: Month and segment identify each row; units are the measure.

New code: no — used preexisting extractors.

Fill validation (agent):
  • https://vahan.example/ev/monthly — **ok** (fill rate 97%)
    One 3W month shows no figure on the page.
  • https://autodata.example/india/ev-sales — **ok** (fill rate 94%)
    June 2024 is blank at the source.

--- Master dataset (54 rows) ---
All sources merged; \`source\` and \`source_url\` identify origin.

| month | segment | units_sold | yoy_growth | source | source_url |
| --- | --- | --- | --- | --- | --- |
| Jan 2024 | 2W | 82,000 | — | Vahan EV dashboard | https://vahan.example/ev/monthly |`
