/**
 * Reads the backend's first-pass run report (bot message text written by discovery/format_report.py and
 * extraction/format.py) back into structure: which websites were validated, how they scored, which were
 * rejected and why, and how full each source's rows were. The backend has no sources endpoint yet; this is
 * the same information, from the text it already sends.
 */
export interface ReportSource {
  rank: number
  title: string
  url: string
  access?: string
  quality?: number
  authority?: number
  relevance?: number
  completeness?: string
  format?: string
  pagesInspected?: number
  likelyFields: string[]
  notes?: string
  whatWeSee?: string
  bestMethod?: string
  confidence?: number
  blockers: string[]
}

export interface RejectedSource {
  title: string
  url: string
  reason: string
}

export interface FillCheck {
  url: string
  status: string
  /** Percent, 0–100, as the backend reported it. */
  fillRate: number
  summary?: string
}

export interface RunReport {
  goal?: string
  status?: string
  strategies: string[]
  sources: ReportSource[]
  rejected: RejectedSource[]
  /** "… and 12 more": rejected sources the backend didn't list. */
  rejectedMore: number
  fills: FillCheck[]
  expectedRows?: number
  actualRows?: number
  columns: string[]
}

const num = (s: string | undefined) => (s === undefined ? undefined : Number(s))

export function parseRunReport(text: string): RunReport | null {
  if (!/=== AWDAX SOURCE DISCOVERY ===|VALIDATED SOURCES \(\d+\)/.test(text)) return null
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const report: RunReport = { strategies: [], sources: [], rejected: [], rejectedMore: 0, fills: [], columns: [] }
  let section: 'head' | 'strategies' | 'validated' | 'rejected' | 'fills' | 'other' = 'head'
  let src: ReportSource | null = null
  let rej: Partial<RejectedSource> | null = null
  let m: RegExpExecArray | null

  const flushRej = () => {
    if (rej?.title && rej.url) report.rejected.push({ title: rej.title, url: rej.url, reason: rej.reason ?? '' })
    rej = null
  }

  for (const raw of lines) {
    const line = raw.trimEnd()
    const t = line.trim()
    if ((m = /^Goal: (.*)$/.exec(t)) && section === 'head') report.goal = m[1]
    else if ((m = /^Status: (\w+)/.exec(t)) && section === 'head') report.status = m[1]
    else if (/^Discovery strategies/.test(t)) section = 'strategies'
    else if (/^VALIDATED SOURCES \(\d+\)/.test(t)) section = 'validated'
    else if (/^REJECTED \(\d+\)/.test(t)) {
      section = 'rejected'
      src = null
    } else if (/^Fill validation/.test(t)) {
      flushRej()
      section = 'fills'
    } else if (/^=== AWDAX EXTRACTION ===|^Extractors \/ methods|^--- Master dataset/.test(t)) {
      flushRej()
      section = 'other'
    }
    if ((m = /^Expected rows \(pre-extract\): ~(\d+)/.exec(t))) report.expectedRows = Number(m[1])
    if ((m = /^Actual rows extracted: (\d+)/.exec(t))) report.actualRows = Number(m[1])
    if ((m = /^Columns: (.+)$/.exec(t)) && !report.columns.length) report.columns = m[1].split(/,\s*/)

    if (section === 'strategies' && (m = /^•\s+(.+)$/.exec(t))) report.strategies.push(m[1])
    else if (section === 'validated') {
      if ((m = /^\[(\d+)\]\s+(.+)$/.exec(t))) {
        src = { rank: Number(m[1]), title: m[2], url: '', likelyFields: [], blockers: [] }
        report.sources.push(src)
      } else if (src) {
        if ((m = /^URL: (\S+)/.exec(t)) && !src.url) src.url = m[1]
        else if ((m = /^Access: (\S+)/.exec(t))) src.access = m[1]
        else if ((m = /^Quality: (\d+)\/10 · Authority: (\d+)\/10 · Relevance: (\d+)\/10/.exec(t))) {
          ;[src.quality, src.authority, src.relevance] = [num(m[1]), num(m[2]), num(m[3])]
        } else if ((m = /^Completeness: (\S+) · Format: (\S+)/.exec(t))) [src.completeness, src.format] = [m[1], m[2]]
        else if ((m = /^Pages inspected: (\d+)/.exec(t))) src.pagesInspected = Number(m[1])
        else if ((m = /^Likely fields: (.+)$/.exec(t))) src.likelyFields = m[1] === '—' ? [] : m[1].split(/,\s*/)
        else if ((m = /^Notes: (.*)$/.exec(t))) src.notes = m[1]
        else if ((m = /^What we see: (.*)$/.exec(t))) src.whatWeSee = m[1]
        else if ((m = /^Best extraction: (.+?)(?: \(confidence (\d+)\/10\))?$/.exec(t))) [src.bestMethod, src.confidence] = [m[1], num(m[2])]
        else if ((m = /^Blockers: (.+)$/.exec(t))) src.blockers = m[1].split(/;\s*/)
      }
    } else if (section === 'rejected') {
      if ((m = /^•\s+(.+)$/.exec(t))) {
        flushRej()
        rej = { title: m[1] }
      } else if ((m = /^… and (\d+) more/.exec(t))) report.rejectedMore = Number(m[1])
      else if (rej && (m = /^Reason: (.*)$/.exec(t))) rej.reason = m[1]
      else if (rej && !rej.url && /^\S+:\/\/\S+$/.test(t)) rej.url = t
    } else if (section === 'fills') {
      if ((m = /^•\s+(\S+) — \*\*(.+?)\*\* \(fill rate (\d+)%\)/.exec(t))) {
        report.fills.push({ url: m[1], status: m[2], fillRate: Number(m[3]) })
      } else if (t && !t.startsWith('-') && report.fills.length && !report.fills[report.fills.length - 1].summary) {
        report.fills[report.fills.length - 1].summary = t
      }
    }
  }
  flushRej()
  return report
}

/** Everything before the master dataset table: the rows themselves are in the dashboard, not the thread. */
export function withoutMasterTable(text: string): { text: string; removedRows: number | null } {
  const at = text.search(/^--- Master dataset \((\d+) rows\) ---$/m)
  if (at < 0) return { text, removedRows: null }
  const rows = Number(/--- Master dataset \((\d+) rows\) ---/.exec(text)![1])
  return { text: text.slice(0, at).trimEnd(), removedRows: rows }
}
