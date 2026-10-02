import { siteOf } from '../../analytics/aggregate.ts'
import { div, fromInt, mul } from '../../analytics/decimal.ts'
import type { Dec } from '../../analytics/decimal.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { FillCheck, ReportSource, RunReport } from '../../analytics/runReport.ts'
import { sourceColumn } from '../../analytics/suggest.ts'

/** A page the backend was reading, from the live stream's `current_source`. */
export interface Visit {
  source: string
  at: string
  phase?: string
}

export type SourceState = 'reading' | 'used' | 'validated' | 'visited' | 'rejected'

/** One website, with everything known about it from the report, the rows and the live stream. */
export interface SourceView {
  site: string
  url: string
  title: string
  state: SourceState
  /** Rows in the table that came from this site, counted exactly. */
  rows: number
  /** Percent of all rows, to two decimals. */
  share: Dec | null
  report?: ReportSource
  fill?: FillCheck
  reason?: string
  rankReasons?: string[]
  /** How the page was found: search, preferred, crawl, and so on. */
  origin?: string
  /** Rows the interactive pass added after the fast read. */
  deepAccepted?: number
  deepNotes?: string[]
  apiStatus?: string
  lastSeen?: string
}

const ORDER: Record<SourceState, number> = { reading: 0, used: 1, validated: 2, visited: 3, rejected: 4 }
const isUrl = (s: string) => /^[a-z][a-z0-9+.-]*:\/\//i.test(s) || /^www\./i.test(s)

/**
 * Every website involved in a chat, merged by site: validated and rejected ones from the run report, row
 * counts from the table's source column, and pages seen live. Rows are counted, never estimated.
 */
export function buildSources(input: { report: RunReport | null; profile?: TableProfile; visits: Visit[]; current?: string; working: boolean }): SourceView[] {
  const { report, profile, visits, current, working } = input
  const bySite = new Map<string, SourceView>()
  const get = (url: string, title: string, state: SourceState): SourceView => {
    const site = siteOf(url)
    let v = bySite.get(site)
    if (!v) {
      v = { site, url, title, state, rows: 0, share: null }
      bySite.set(site, v)
    }
    return v
  }

  for (const s of report?.sources ?? []) {
    const v = get(s.url, s.title, 'validated')
    v.report = s
    v.title = s.title
    v.fill = report?.fills.find((f) => siteOf(f.url) === v.site)
  }

  // Exact rows per site from the table itself (the backend adds source_url to every merged row).
  const col = profile ? sourceColumn(profile) : undefined
  if (profile && col) {
    const nameCol = profile.columns.find((c) => /^source(_name)?$/i.test(c.name) && c.kind !== 'url')
    col.labels.forEach((label, row) => {
      if (!label) return
      const v = get(label, nameCol?.labels[row] || siteOf(label), 'used')
      v.rows++
      if (v.state !== 'rejected') v.state = 'used'
    })
    const total = profile.rowCount
    for (const v of bySite.values()) if (v.rows) v.share = div(mul(fromInt(v.rows), fromInt(100)), fromInt(total), 2)
  }

  for (const visit of visits) {
    if (!isUrl(visit.source)) continue
    const v = get(visit.source, siteOf(visit.source), 'visited')
    v.lastSeen = visit.at
  }
  for (const r of report?.rejected ?? []) {
    const v = get(r.url, r.title, 'rejected')
    if (!v.report) v.title = r.title
    if (!v.rows) {
      v.state = 'rejected'
      v.reason = r.reason
    }
  }
  if (working && current) {
    // The live stream sends either a URL or a source's title while extracting.
    const hit = isUrl(current) ? bySite.get(siteOf(current)) ?? get(current, siteOf(current), 'reading') : [...bySite.values()].find((v) => v.title === current)
    if (hit) hit.state = 'reading'
  }

  return [...bySite.values()].sort((a, b) => ORDER[a.state] - ORDER[b.state] || b.rows - a.rows || (a.report?.rank ?? 99) - (b.report?.rank ?? 99))
}

const API_STATE: Record<string, SourceState> = {
  inspecting: 'reading',
  validated: 'validated',
  complete: 'used',
  partial: 'used',
  empty: 'visited',
  selected: 'reading',
  skipped: 'visited',
  blocked: 'rejected',
  failed: 'rejected',
}

/**
 * Overlay AwdaxP source rows (interactive pass, origin, rank) onto the websites already shown. A run that stopped
 * leaves its last source "inspecting" in the backend's list; once nothing is `working`, that reads as visited, not
 * "Reading now".
 */
export function overlaySources(
  views: SourceView[],
  api: { url: string; title: string; status: string; accepted: number; reason: string; domain: string; origin: string; rank_reasons?: string[]; deep_accepted: number; deep_notes: string[] }[] | undefined,
  working = true,
): SourceView[] {
  if (!api?.length) return views
  const stateOf = (status: string): SourceState | undefined => {
    const s = API_STATE[status]
    return s === 'reading' && !working ? 'visited' : s
  }
  const next = views.map((view) => ({ ...view }))
  const bySite = new Map(next.map((view) => [view.site, view]))
  for (const item of api) {
    const site = siteOf(item.url || item.domain)
    let view = bySite.get(site)
    if (!view) {
      view = { site, url: item.url, title: item.title || site, state: stateOf(item.status) ?? 'visited', rows: item.accepted, share: null, reason: item.reason }
      next.push(view)
      bySite.set(site, view)
    }
    view.origin = item.origin
    view.deepAccepted = item.deep_accepted
    view.deepNotes = item.deep_notes
    view.rankReasons = item.rank_reasons
    view.apiStatus = item.status
    if (!view.rows && view.state !== 'rejected') view.state = stateOf(item.status) ?? view.state
    if (item.accepted > view.rows) view.rows = item.accepted
    if ((item.status === 'blocked' || item.status === 'failed') && item.reason && !item.accepted && !view.rows) {
      view.state = 'rejected'
      view.reason = item.reason
    }
  }
  return next.sort((a, b) => ORDER[a.state] - ORDER[b.state] || b.rows - a.rows || (a.report?.rank ?? 99) - (b.report?.rank ?? 99))
}

/** How a site was read, in the design system's method colours (DESIGN_SYSTEM "Highlighters"). */
export function methodOf(access?: string): { label: string; tone: 'structured' | 'content' | 'rendered' | 'ai' | null } {
  switch (access) {
    case 'api':
    case 'file_download':
      return { label: access === 'api' ? 'API (structured data)' : 'File download (structured data)', tone: 'structured' }
    case 'http_static':
      return { label: 'Page content (plain HTML)', tone: 'content' }
    case 'js_rendered':
      return { label: 'Rendered page (headless browser)', tone: 'rendered' }
    case 'login_required':
      return { label: 'Needs login (skipped)', tone: null }
    case 'blocked':
      return { label: 'Blocked (skipped)', tone: null }
    default:
      return { label: access ? access.replace(/_/g, ' ') : 'Not reported', tone: null }
  }
}
