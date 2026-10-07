import { defuse } from '../export/formats.ts'

/** A link the run could not read with a plain web request (GET /api/instances/:id/failed-links). */
export interface FailedLink {
  url: string
  domain: string
  /** The run step that asked for it: research, search, inspect or scrape. */
  stage: string
  /** blocked, not found, unreachable, captcha, error or not allowed. */
  outcome: string
  http_status: number | ''
  reason: string
  checked_at: string
}

/** One website the web-research step ranked; discovery tries them in rank order. */
export interface ResearchSite {
  rank: number
  url: string
  domain?: string
  site_name?: string
  what_it_has?: string
  format?: string
  why?: string
  /** "yes" when the site appeared in the Google results the model searched. */
  grounded?: string
}

export interface FailedLinksResponse {
  columns: string[]
  column_labels: string[]
  rows: FailedLink[]
  row_count: number
  research: ResearchSite[]
}

const CSV_COLUMNS: (keyof FailedLink)[] = ['url', 'domain', 'stage', 'outcome', 'http_status', 'reason', 'checked_at']

/** The failed links as CSV (UTF-8 with a byte-order mark, so Excel reads it). Cells are scraped text, so formulas are defused. */
export function failedLinksCsv(res: Pick<FailedLinksResponse, 'columns' | 'column_labels' | 'rows'>): string {
  const labels = CSV_COLUMNS.map((c) => res.column_labels[res.columns.indexOf(c)] || c)
  const cell = (v: string | number) => {
    const s = defuse(String(v ?? ''))
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const lines = [labels.map(cell), ...res.rows.map((r) => CSV_COLUMNS.map((c) => cell(r[c])))]
  return `\ufeff${lines.map((l) => l.join(',')).join('\r\n')}`
}
