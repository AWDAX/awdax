import type { Filter } from '../../analytics/aggregate.ts'
import { groupKey } from '../../analytics/profile.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { categories, timeColumn } from '../../analytics/suggest.ts'

/** Dashboard-wide filters, like Power BI slicers. They apply to every tile and the data table. */
export interface SlicerState {
  search: string
  /** Column index → picked group keys. Empty or missing means "all". */
  picks: Record<number, string[]>
  /** Period keys, inclusive. */
  from?: string
  to?: string
}

export const EMPTY_SLICERS: SlicerState = { search: '', picks: {} }

/** The columns worth a slicer: up to three category columns and the timeline. */
export function slicerColumns(p: TableProfile) {
  return { cats: categories(p).slice(0, 3), time: timeColumn(p) }
}

/** Distinct values of a column with their row counts, most common first. */
export function valuesOf(p: TableProfile, column: number): { key: string; label: string; count: number }[] {
  const col = p.columns[column]
  const out = new Map<string, { key: string; label: string; count: number }>()
  col.labels.forEach((label) => {
    if (!label) return
    const key = groupKey(label)
    const v = out.get(key) ?? { key, label, count: 0 }
    v.count++
    out.set(key, v)
  })
  return [...out.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}

/** The period keys of the time column, in time order. */
export function periodKeys(p: TableProfile, column: number): { key: string; label: string }[] {
  const seen = new Map<string, string>()
  for (const x of p.columns[column].periods ?? []) if (x) seen.set(x.key, x.label)
  return [...seen.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, label]) => ({ key, label }))
}

export function toFilters(p: TableProfile, s: SlicerState): Filter[] {
  const out: Filter[] = []
  if (s.search.trim()) out.push({ column: -1, op: 'search', values: [s.search] })
  for (const [col, keys] of Object.entries(s.picks)) if (keys.length) out.push({ column: Number(col), op: 'in', values: keys })
  const time = timeColumn(p)
  if (time && (s.from || s.to)) {
    const keys = periodKeys(p, time.index)
      .map((k) => k.key)
      .filter((k) => (!s.from || k >= s.from) && (!s.to || k <= s.to))
    out.push({ column: time.index, op: 'in', values: keys })
  }
  return out
}

export const activeCount = (s: SlicerState) =>
  (s.search.trim() ? 1 : 0) + Object.values(s.picks).filter((v) => v.length).length + (s.from || s.to ? 1 : 0)
