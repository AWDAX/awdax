import type { Query } from './aggregate.ts'
import { AGG_LABEL } from './aggregate.ts'
import { isMeasure, lc } from './profile.ts'
import type { ColumnProfile, TableProfile } from './profile.ts'
import { bucketOf } from './period.ts'
import type { Bucket } from './period.ts'
import type { ChartSpec, ChartType } from './spec.ts'

/**
 * Chart suggestions and follow-up questions, read off the table's shape. Nothing here is guessed from
 * the data's meaning: a trend needs a time column, a ranking needs a category, a total needs a measure.
 */

const KIND_ORDER = { money: 0, number: 1, percent: 2 } as Record<string, number>

const MEASURE_NAME = /units|sales|sold|revenue|price|amount|value|total|count|qty|quantity|volume|cost|salary|stipend|funding|registrations|downloads|views|score/i

/**
 * Measures worth adding up, best first: money, then columns named like a measure (units, sales, price…),
 * then plain numbers, then percentages; among equals, the one whose values vary most.
 */
export function measures(p: TableProfile): ColumnProfile[] {
  const rank = (c: ColumnProfile) => (c.kind === 'money' ? 0 : MEASURE_NAME.test(c.name) ? 0.5 : KIND_ORDER[c.kind])
  return p.columns.filter(isMeasure).sort((a, b) => rank(a) - rank(b) || b.distinct - a.distinct || b.filled - a.filled)
}

/** The best time axis: a joined Month + Year beats either alone; a month-name-only column comes last. */
export function timeColumn(p: TableProfile): ColumnProfile | undefined {
  const periods = p.columns.filter((c) => c.kind === 'period' && c.distinct >= 2)
  const rank = (c: ColumnProfile) => (c.virtual ? 0 : c.grain === 'monthName' ? 3 : c.grain === 'year' ? 2 : 1)
  return periods.sort((a, b) => rank(a) - rank(b) || b.distinct - a.distinct)[0]
}

/** Category columns with 2–30 groups, fewest groups first (easiest to read). */
export function categories(p: TableProfile): ColumnProfile[] {
  return p.columns
    .filter((c) => (c.kind === 'category' || (c.kind === 'text' && c.distinct <= 30)) && c.distinct >= 2 && c.distinct <= 30)
    .sort((a, b) => a.distinct - b.distinct)
}

/** Percentages and elapsed times read best as averages in an automatic summary. */
export const defaultAgg = (m: ColumnProfile | undefined): Query['agg'] => (!m ? 'count' : m.kind === 'percent' || m.suffix === 'min' ? 'avg' : 'sum')

export function measureTitle(p: TableProfile, q: Query): string {
  if (q.agg === 'count' || q.measure === undefined) return 'Rows'
  const m = p.columns[q.measure]
  if (q.agg === 'distinct') return m?.kind === 'url' ? 'Websites' : `Distinct ${m ? lc(m.label) : 'values'}`
  const word = q.agg === 'sum' ? 'Total' : AGG_LABEL[q.agg]
  return `${word} ${m ? lc(m.label) : ''}`.trim()
}

export function queryTitle(p: TableProfile, q: Query): string {
  const what = measureTitle(p, q)
  if (q.groupBy === undefined) return what
  const g = p.columns[q.groupBy]
  return `${what} by ${g ? lc(g.label) : ''}`
}

let n = 0
const id = () => `s${(n++).toString(36)}`

function spec(p: TableProfile, type: ChartType, query: Query, reason: string, labels?: boolean): ChartSpec {
  return { id: id(), type, title: queryTitle(p, query), reason, query, labels }
}

/** The column naming each row's website: the backend's merged tables carry `source_url` (or `source`). */
export function sourceColumn(p: TableProfile): ColumnProfile | undefined {
  const urls = p.columns.filter((c) => c.kind === 'url' && !c.virtual)
  return urls.find((c) => /source|origin|site|link|url/i.test(c.name)) ?? urls[0]
}

/**
 * How to group a timeline so a chart stays readable and exact: one point per day only when there are few
 * days; otherwise per month (up to three years) or per year.
 */
export function timeBucket(time: ColumnProfile): Bucket | undefined {
  if (time.grain !== 'day' && time.grain !== 'month') return undefined
  const months = new Set((time.periods ?? []).filter(Boolean).map((x) => bucketOf(x!, 'month').key)).size
  if (time.grain === 'month') return months > 48 ? 'year' : undefined
  if (time.distinct <= 16) return undefined
  return months >= 3 && months <= 36 ? 'month' : 'year'
}

/**
 * Ideas for a one-screen dashboard, in page order: up to four number cards (total, average, rows, sources),
 * then charts (trend, share, ranking, rows per source, averages, scatter), then extras. Charts with few
 * points show their exact values on the marks.
 */
export function suggestCharts(p: TableProfile): ChartSpec[] {
  const kpis: ChartSpec[] = []
  const charts: ChartSpec[] = []
  const [m, m2] = measures(p)
  const time = timeColumn(p)
  const cats = categories(p)
  const src = sourceColumn(p)
  const agg = defaultAgg(m)
  const measure = m?.index

  if (m) kpis.push(spec(p, 'kpi', { measure, agg }, `${m.label} is the main measure, so its ${agg === 'sum' ? 'total' : 'average'} leads.`))
  if (m && agg === 'sum') kpis.push(spec(p, 'kpi', { measure, agg: 'avg' }, 'The average per row, so one large value can’t hide.'))
  kpis.push(spec(p, 'kpi', { agg: 'count' }, 'How many rows were collected.'))
  if (src && src.distinct > 0) kpis.push(spec(p, 'kpi', { measure: src.index, agg: 'distinct' }, 'How many websites the rows came from.'))

  // A date on nearly every row (launch dates, posting dates) marks events, not a series over time: count
  // rows per year or month instead of adding up a measure by each date.
  const eventDates = time && time.grain === 'day' && p.rowCount > 5 && time.distinct >= p.rowCount * 0.8
  if (time && eventDates) {
    const months = new Set((time.periods ?? []).filter(Boolean).map((x) => bucketOf(x!, 'month').key)).size
    const bucket: Bucket = months > 24 ? 'year' : 'month'
    const q: Query = { groupBy: time.index, agg: 'count', sort: 'time', bucket }
    charts.push({ ...spec(p, 'column', q, `Rows per ${bucket} of ${lc(time.label)}: each row has its own date, so counting per ${bucket} shows the pattern.`, true), title: `Rows per ${bucket}, by ${lc(time.label)}` })
  } else if (time) {
    const bucket = timeBucket(time)
    const points = bucket ? new Set((time.periods ?? []).filter(Boolean).map((x) => bucketOf(x!, bucket).key)).size : time.distinct
    const q: Query = { groupBy: time.index, measure, agg, sort: 'time', bucket }
    const title = `${queryTitle(p, q)}${bucket ? `, per ${bucket}` : ''}`
    charts.push({ ...spec(p, points > 24 ? 'area' : 'line', q, `A timeline${bucket ? ` grouped by ${bucket}` : ''}; missing periods show as gaps, not as zeros.`, points <= 12), title })
  }
  const cat = cats[0]
  const small = cats.find((c) => c.distinct <= 6)
  if (small) {
    charts.push(spec(p, 'donut', { groupBy: small.index, measure: agg === 'sum' ? measure : undefined, agg: agg === 'sum' ? 'sum' : 'count' },
      `A donut, because ${small.label} has only ${small.distinct} groups to share out.`, true))
  }
  const rank = cats.find((c) => c !== small) ?? cat
  if (rank && m) {
    const long = rank.distinct > 6 || rank.labels.some((l) => l.length > 14)
    charts.push(spec(p, long ? 'bar' : 'column', { groupBy: rank.index, measure, agg, sort: 'value-desc', limit: 10, other: true },
      `Ranked, because ${rank.label} names ${rank.distinct} groups; groups past the top 10 add up in Other.`, true))
  }
  if (src && src.distinct > 1) {
    charts.push(spec(p, 'bar', { groupBy: src.index, agg: 'count', sort: 'value-desc', limit: 10, other: true }, 'How many rows each website gave.', true))
  }
  if (m && cat) {
    charts.push(spec(p, 'column', { groupBy: cat.index, measure, agg: 'avg', sort: 'value-desc', limit: 10 }, 'Averages, so large groups don’t win just by having more rows.', true))
  }
  if (m && m2) {
    charts.push({ ...spec(p, 'scatter', { agg: 'count' }, `A scatter, to see whether ${m.label} moves with ${m2.label}.`), x: m2.index, y: m.index, title: `${m.label} against ${m2.label}` })
  }
  if (cat && !m) {
    charts.push(spec(p, 'bar', { groupBy: cat.index, agg: 'count', sort: 'value-desc', limit: 10, other: true }, `How many rows each ${lc(cat.label)} has.`, true))
  }
  const table = { ...spec(p, 'table', { agg: 'count' }, 'Every row, exactly as scraped.'), title: 'All rows' }
  return [...kpis.slice(0, 4), ...charts, table]
}

export type Intent = 'top' | 'bottom' | 'total' | 'average' | 'trend' | 'count' | 'compare' | 'share' | 'list'

export interface FollowUp {
  id: string
  text: string
  intent: Intent
  query: Query
  chart: ChartType
}

/** Questions a person would ask next about this table, each answerable exactly from it. */
export function suggestFollowUps(p: TableProfile): FollowUp[] {
  const out: FollowUp[] = []
  const [m] = measures(p)
  const time = timeColumn(p)
  const cats = categories(p)
  // A ranking of two is trivial; ask about the first category with three or more groups when there is one.
  const cat = cats.find((c) => c.distinct >= 3) ?? cats[0]
  const other = cats.find((c) => c !== cat)
  const agg = defaultAgg(m)
  const mLabel = m ? lc(m.label) : ''
  const push = (text: string, intent: Intent, query: Query, chart: ChartType) => out.push({ id: id(), text, intent, query, chart })

  if (m && cat) {
    push(`Which ${lc(cat.label)} has the highest ${mLabel}?`, 'top', { groupBy: cat.index, measure: m.index, agg, sort: 'value-desc', limit: 1 }, 'bar')
  }
  if (m && time) {
    const bucket = timeBucket(time)
    const unit = bucket ?? (time.grain === 'day' ? 'date' : time.grain === 'monthName' ? 'month' : time.grain === 'fiscal' ? 'financial year' : time.grain)
    push(`How did ${mLabel} change over time?`, 'trend', { groupBy: time.index, measure: m.index, agg, sort: 'time', bucket }, 'line')
    push(`Which ${unit} had the lowest ${mLabel}?`, 'bottom', { groupBy: time.index, measure: m.index, agg, sort: 'value-asc', limit: 1, bucket }, 'column')
  }
  if (m) push(`What is the ${agg === 'sum' ? 'total' : 'average'} ${mLabel}?`, agg === 'sum' ? 'total' : 'average', { measure: m.index, agg }, 'kpi')
  if (m && cat) push(`What's the average ${mLabel} per ${lc(cat.label)}?`, 'average', { groupBy: cat.index, measure: m.index, agg: 'avg', sort: 'value-desc' }, 'column')
  const counted = other ?? cat
  if (counted) push(`How many rows per ${lc(counted.label)}?`, 'count', { groupBy: counted.index, agg: 'count', sort: 'value-desc' }, 'bar')
  const shared = [cat, other].find((c) => c && c.distinct <= 6)
  if (m && shared) {
    push(`What share of ${mLabel} does each ${lc(shared.label)} have?`, 'share', { groupBy: shared.index, measure: m.index, agg: 'sum' }, 'donut')
  }
  if (m && cat && cat.distinct > 5) {
    push(`Top 5 ${lc(cat.label)} by ${mLabel}`, 'top', { groupBy: cat.index, measure: m.index, agg, sort: 'value-desc', limit: 5 }, 'bar')
  }
  if (!m) push('How many rows are there?', 'count', { agg: 'count' }, 'kpi')
  return out.slice(0, 6)
}
