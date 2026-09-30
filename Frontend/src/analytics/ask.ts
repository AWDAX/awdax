import type { Filter, Query } from './aggregate.ts'
import { toString } from './decimal.ts'
import { parseNumber } from './parse.ts'
import { groupKey, isMeasure } from './profile.ts'
import type { ColumnProfile, TableProfile } from './profile.ts'
import type { ChartType } from './spec.ts'
import { categories, defaultAgg, measures, timeColumn } from './suggest.ts'
import type { Intent } from './suggest.ts'

/**
 * Plain-English questions → an exact query. Deterministic on purpose: the same words always give the same
 * numbers, and a question it can't read says so instead of guessing (the query builder covers the rest).
 */
export type Parsed = { ok: true; intent: Intent; query: Query; chart: ChartType } | { ok: false; hint: string }

const STOP = new Set(['the', 'a', 'an', 'of', 'in', 'on', 'for', 'by', 'per', 'to', 'and', 'or', 'is', 'are', 'what', 'which', 'how', 'with', 'each', 'every', 'show', 'me', 'all', 'from', 'total', 'number'])
const stem = (w: string) => w.replace(/(ies)$/, 'y').replace(/(es|s)$/, '')
const tokens = (s: string) => s.toLowerCase().split(/[^a-z0-9₹%]+/).filter(Boolean).map(stem)

const SYNONYMS: Record<string, string[]> = {
  price: ['cost', 'priced', 'expensive', 'cheap', 'cheapest', 'costliest', 'pricey'],
  sale: ['sold', 'sell', 'selling'],
  unit: ['units', 'volume'],
  range: ['km', 'mileage'],
  count: ['number'],
}

function mentions(col: ColumnProfile, q: string[]): number {
  const words = tokens(col.label).filter((w) => !STOP.has(w))
  if (words.length === 0) return 0
  const hits = words.filter((w) => q.includes(w) || (SYNONYMS[w] ?? []).some((s) => q.includes(stem(s)))).length
  return hits / words.length
}

const INTENTS: [Intent, RegExp][] = [
  ['compare', /\b(compare|vs\.?|versus|against)\b/],
  ['trend', /\b(trend|over time|change[ds]?|growth|grew|monthly|yearly|over the (months|years)|timeline)\b/],
  ['share', /\b(share|percentage|proportion|breakdown|split|distribution)\b/],
  ['bottom', /\b(lowest|least|min(imum)?|smallest|fewest|bottom|worst|cheapest|shortest)\b/],
  ['top', /\b(highest|most|max(imum)?|largest|biggest|top|best|costliest|longest|leading)\b/],
  ['average', /\b(average|avg|mean|typical)\b/],
  ['count', /\b(how many|count|number of)\b/],
  ['total', /\b(total|sum|overall|altogether|combined)\b/],
]

function numberAfter(text: string, words: RegExp): string | undefined {
  const m = new RegExp(`${words.source}\\s*(₹|rs\\.?|\\$)?\\s*([\\d.,]+\\s*(lakh|lac|cr|crore|k|m|million|bn)?)`, 'i').exec(text)
  if (!m) return undefined
  const r = parseNumber(m[3])
  return r.ok ? toString(r.num.value) : undefined
}

export function parseQuestion(p: TableProfile, text: string): Parsed {
  const lower = text.toLowerCase().replace(/[?!]/g, ' ')
  const q = tokens(lower)
  if (q.length === 0) return { ok: false, hint: 'Type a question about this table.' }

  const intent: Intent = INTENTS.find(([, re]) => re.test(lower))?.[0] ?? 'list'
  const filters: Filter[] = []

  // Values named in the question become filters: "for Tata", "in 2024", "Tata vs MG".
  const valueCols: { col: ColumnProfile; keys: string[] }[] = []
  for (const col of p.columns.filter((c) => c.kind === 'category' || (c.kind === 'text' && c.distinct <= 200))) {
    const keys = [...new Set(col.labels.map(groupKey))].filter((k) => k && new RegExp(`(^|[^a-z0-9])${k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}($|[^a-z0-9])`).test(lower))
    if (keys.length) valueCols.push({ col, keys })
  }
  const years = [...lower.matchAll(/\b(19|20)\d{2}\b/g)].map((m) => Number(m[0]))
  const time = timeColumn(p)
  if (years.length && time?.periods) {
    const keys = [...new Set(time.periods.filter((x) => x && x.year !== undefined && years.includes(x.year)).map((x) => x!.key))]
    if (keys.length) filters.push({ column: time.index, op: 'in', values: keys })
  }

  // Columns named in the question.
  const scored = p.columns.map((c) => ({ c, s: mentions(c, q) })).filter((x) => x.s >= 0.5)
  const named = scored.sort((a, b) => b.s - a.s).map((x) => x.c)
  const measure = named.find(isMeasure) ?? measures(p)[0]

  const above = numberAfter(lower, /(above|over|more than|greater than|at least|>=?)/)
  const below = numberAfter(lower, /(below|under|less than|at most|<=?)/)
  if (measure && above) filters.push({ column: measure.index, op: 'gte', values: [above] })
  if (measure && below) filters.push({ column: measure.index, op: 'lte', values: [below] })

  // Grouping: "by X", "per X", "each X", "which X", or the named category for a ranking.
  const byWord = /\b(by|per|each|every|across|which|what)\s+([a-z][a-z ]{1,30})/.exec(lower)
  let group: ColumnProfile | undefined
  if (byWord) group = p.columns.find((c) => c !== measure && !isMeasure(c) && mentions(c, tokens(byWord[2])) >= 0.5)
  if (!group && intent === 'trend') group = time
  if (!group) group = named.find((c) => c !== measure && (c.kind === 'category' || c.kind === 'period'))

  if (intent === 'compare') {
    const target = valueCols.find((v) => v.keys.length >= 2)
    if (!target) return { ok: false, hint: 'Name two values to compare, e.g. “Tata vs MG”.' }
    filters.push({ column: target.col.index, op: 'in', values: target.keys.slice(0, 2) })
    return { ok: true, intent, chart: 'column', query: { groupBy: target.col.index, measure: measure?.index, agg: defaultAgg(measure), filters, sort: 'value-desc' } }
  }
  // A single value named without "by X" filters to it: "total sales for Tata".
  for (const v of valueCols) if (v.col !== group) filters.push({ column: v.col.index, op: 'in', values: v.keys })

  const agg: Query['agg'] =
    intent === 'count' ? 'count' : intent === 'average' ? 'avg' : !measure ? 'count' : defaultAgg(measure)
  const topN = /\b(top|bottom)\s+(\d{1,2})\b/.exec(lower)
  const limit = topN ? Number(topN[2]) : undefined

  if (intent === 'top' || intent === 'bottom') {
    group ??= categories(p)[0] ?? time
    if (!group) return { ok: true, intent, chart: 'kpi', query: { measure: measure?.index, agg: intent === 'top' ? 'max' : 'min', filters } }
    return {
      ok: true, intent, chart: 'bar',
      query: { groupBy: group.index, measure: measure?.index, agg, filters, sort: intent === 'top' ? 'value-desc' : 'value-asc', limit: limit ?? 1 },
    }
  }
  if (intent === 'trend') {
    if (!group || group.kind !== 'period') return { ok: false, hint: 'This table has no date or period column to show a trend over.' }
    return { ok: true, intent, chart: 'line', query: { groupBy: group.index, measure: measure?.index, agg, filters, sort: 'time' } }
  }
  if (intent === 'share') {
    group ??= categories(p)[0]
    if (!group) return { ok: false, hint: 'Say what to split by, e.g. “share of sales by brand”.' }
    return { ok: true, intent, chart: 'donut', query: { groupBy: group.index, measure: measure?.index, agg: measure ? 'sum' : 'count', filters } }
  }
  if (group) {
    return { ok: true, intent, chart: group.kind === 'period' ? 'line' : 'bar', query: { groupBy: group.index, measure: measure?.index, agg, filters, limit } }
  }
  if (intent === 'list' && !named.length && !filters.length) {
    return { ok: false, hint: 'Try “highest price by brand”, “total units in 2024” or “how many rows per type”.' }
  }
  return { ok: true, intent: intent === 'list' ? 'total' : intent, chart: 'kpi', query: { measure: measure?.index, agg, filters } }
}
