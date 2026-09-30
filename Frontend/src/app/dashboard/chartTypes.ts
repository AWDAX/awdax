import type { Query } from '../../analytics/aggregate.ts'
import { isGroupable, isMeasure } from '../../analytics/profile.ts'
import type { ColumnProfile, TableProfile } from '../../analytics/profile.ts'
import type { ChartType } from '../../analytics/spec.ts'

/** The "Add charts" gallery, in Power BI's order: comparisons, trends, parts of a whole, then the rest. */
export const GALLERY: { type: ChartType; best: string }[] = [
  { type: 'column', best: 'Compare groups side by side' },
  { type: 'bar', best: 'Rank groups with long names' },
  { type: 'line', best: 'A value over time' },
  { type: 'area', best: 'Volume over time' },
  { type: 'pie', best: 'Share of a whole, few groups' },
  { type: 'donut', best: 'Share of a whole, with the total' },
  { type: 'scatter', best: 'Two numbers against each other' },
  { type: 'kpi', best: 'One headline number' },
  { type: 'table', best: 'Exact values, grouped or raw' },
]

export type Draft = { query: Query; x?: number; y?: number }

const GROUPED: ChartType[] = ['column', 'bar', 'line', 'area', 'pie', 'donut']

/** Why a chart type can't be drawn from this table, or null when it can. */
export function unavailable(p: TableProfile, type: ChartType): string | null {
  if (type === 'scatter' && p.columns.filter(isMeasure).length < 2) return 'Needs two number columns'
  if (GROUPED.includes(type) && p.columns.filter(isGroupable).length === 0) return 'Needs a column to group by'
  return null
}

const byDistinct = (a: ColumnProfile, b: ColumnProfile) => a.distinct - b.distinct

/** The group column a chart type reads best with: time for trends, few groups for shares, any category else. */
function groupFor(p: TableProfile, type: ChartType, current?: number): number | undefined {
  const groups = p.columns.filter(isGroupable)
  const cur = current !== undefined ? p.columns[current] : undefined
  const time = groups.find((c) => c.kind === 'period')
  const cats = groups.filter((c) => c.kind !== 'period')
  if (type === 'line' || type === 'area') return (cur?.kind === 'period' ? cur : time ?? cur ?? cats[0])?.index
  if (type === 'pie' || type === 'donut') return (cur && cur.kind !== 'period' ? cur : [...cats].sort(byDistinct)[0] ?? time)?.index
  return (cur ?? cats[0] ?? time)?.index
}

/**
 * Fields for a newly picked chart type, keeping what still fits from the current draft: the measure and its
 * aggregate carry over; the group column changes only when the type reads better with another (a trend wants
 * a date, a pie wants few groups).
 */
export function draftFor(p: TableProfile, type: ChartType, from: Draft): Draft {
  const measures = p.columns.filter(isMeasure)
  const measure = from.query.measure ?? measures[0]?.index
  const agg = measure === undefined ? 'count' : from.query.agg === 'count' ? 'sum' : from.query.agg
  if (type === 'scatter') return { query: from.query, x: from.x ?? measures[0]?.index, y: from.y ?? measures[1]?.index }
  if (type === 'kpi') return { query: { measure, agg } }
  if (type === 'table' && from.query.groupBy === undefined) return { query: { measure, agg } }
  const groupBy = groupFor(p, type, from.query.groupBy)
  const col = groupBy !== undefined ? p.columns[groupBy] : undefined
  const keep = groupBy === from.query.groupBy
  const query: Query = { measure, agg, groupBy, bucket: keep ? from.query.bucket : undefined }
  if (col?.kind === 'period') query.sort = 'time'
  else {
    query.sort = keep ? (from.query.sort ?? 'value-desc') : 'value-desc'
    // A pie past six slices is unreadable; the rest add up in Other.
    if ((type === 'pie' || type === 'donut') && col && col.distinct > 6) Object.assign(query, { limit: 5, other: true })
    else if (keep) Object.assign(query, { limit: from.query.limit, other: from.query.other })
  }
  return { query }
}
