import { formatDate, formatMoney, monthLabel } from './format.ts'
import type { CellValue, Column, Dataset, Row } from './types.ts'

/**
 * The charts rule from docs/PRODUCT.md, as code:
 *   date → line (count over time) · number/money → histogram
 *   ordered category → donut (one-hue ramp) · other category / location → bars, top 6 + Other
 * A column with fewer than two groups gets no chart: one bar is a number, not a chart.
 */

export type ChartKind = 'line' | 'histogram' | 'donut' | 'bars'

export interface ChartDatum {
  key: string
  label: string
  value: number
}

export interface ChartSpec {
  kind: ChartKind
  column: Column
  title: string
  /** One sentence under the chart saying why it was chosen. */
  reason: string
  data: ChartDatum[]
  /** Rows with a value for this column. */
  counted: number
  /** Rows left out because the value was not found. */
  missing: number
  /** Largest group in the full dataset, so a chart filling in live never rescales. */
  max: number
}

interface Bucketing {
  kind: ChartKind
  buckets: { key: string; label: string }[]
  keyOf: (v: CellValue) => string
  title: string
  reason: string
}

const OTHER = { key: '__other', label: 'Other' }

function niceStep(raw: number): number {
  const exp = 10 ** Math.floor(Math.log10(raw))
  const f = raw / exp
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * exp
}

function histogram(col: Column, values: number[]): Bucketing {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const step = niceStep((max - min) / 6 || Math.abs(max) || 1)
  const start = Math.floor(min / step) * step
  const count = Math.floor((max - start) / step) + 1
  const fmt = (n: number) =>
    col.type === 'money' ? formatMoney(n, col.currency, true) : Number.isInteger(step) ? String(n) : n.toFixed(1)
  const buckets = Array.from({ length: count }, (_, i) => {
    const lo = start + i * step
    return { key: String(i), label: `${fmt(lo)}–${fmt(lo + step)}` }
  })
  return {
    kind: 'histogram',
    buckets,
    // The epsilon keeps 4.0 out of the 3.8–4.0 bin when 0.2 steps carry float error.
    keyOf: (v) => String(Math.min(count - 1, Math.floor((Number(v) - start) / step + 1e-9))),
    title: `${col.label}, grouped into ranges`,
    reason: `A histogram, because ${col.label} is a ${col.type === 'money' ? 'money' : 'number'} column.`,
  }
}

const utc = (v: CellValue) => new Date(`${String(v).slice(0, 10)}T00:00:00Z`)
const DAY = 86_400_000

function timeline(col: Column, values: CellValue[]): Bucketing {
  const times = values.map((v) => utc(v).getTime())
  const first = new Date(Math.min(...times))
  const last = new Date(Math.max(...times))
  const byDay = (last.getTime() - first.getTime()) / DAY <= 31
  const buckets: { key: string; label: string }[] = []

  if (byDay) {
    for (let t = first.getTime(); t <= last.getTime(); t += DAY) {
      const iso = new Date(t).toISOString().slice(0, 10)
      buckets.push({ key: iso, label: formatDate(iso) })
    }
  } else {
    const d = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth(), 1))
    while (d <= last) {
      buckets.push({ key: d.toISOString().slice(0, 7), label: monthLabel(d.getUTCMonth()) })
      d.setUTCMonth(d.getUTCMonth() + 1)
    }
  }
  const unit = byDay ? 'day' : 'month'
  return {
    kind: 'line',
    buckets,
    keyOf: (v) => utc(v).toISOString().slice(0, byDay ? 10 : 7),
    title: `Count per ${unit}, by ${col.label.toLowerCase()}`,
    reason: `A line chart, because ${col.label} is a date column.`,
  }
}

function categories(col: Column, values: CellValue[]): Bucketing {
  if (col.levels && col.levels.length <= 6) {
    const levels = col.levels
    const outside = values.some((v) => !levels.includes(String(v)))
    return {
      kind: 'donut',
      buckets: [...levels.map((l) => ({ key: l, label: l })), ...(outside ? [OTHER] : [])],
      keyOf: (v) => (levels.includes(String(v)) ? String(v) : OTHER.key),
      title: `Share by ${col.label.toLowerCase()}`,
      reason: `A donut, because ${col.label} has ${levels.length} ordered levels.`,
    }
  }
  const counts = new Map<string, number>()
  for (const v of values) counts.set(String(v), (counts.get(String(v)) ?? 0) + 1)
  const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([k]) => k)
  const top = ranked.slice(0, 6)
  const folded = ranked.length > 6
  return {
    kind: 'bars',
    buckets: [...top.map((k) => ({ key: k, label: k })), ...(folded ? [OTHER] : [])],
    keyOf: (v) => (top.includes(String(v)) ? String(v) : OTHER.key),
    title: `Count by ${col.label.toLowerCase()}`,
    reason:
      `A bar chart, because ${col.label} is a ${col.type} column.` +
      (folded ? ' The top 6 are shown; the rest are grouped as Other.' : ''),
  }
}

function bucketing(col: Column, values: CellValue[]): Bucketing | null {
  if (values.length === 0) return null
  switch (col.type) {
    case 'number':
    case 'money':
      return histogram(col, values.map(Number))
    case 'date':
      return timeline(col, values)
    case 'category':
    case 'location':
      return categories(col, values)
    default:
      return null
  }
}

const valuesOf = (rows: Row[], key: string) =>
  rows.map((r) => r.cells[key]?.value).filter((v): v is CellValue => v !== null && v !== undefined)

function count(b: Bucketing, values: CellValue[]): ChartDatum[] {
  const tally = new Map(b.buckets.map((x) => [x.key, 0]))
  for (const v of values) {
    const k = b.keyOf(v)
    tally.set(k, (tally.get(k) ?? 0) + 1)
  }
  return b.buckets.map((x) => ({ ...x, value: tally.get(x.key) ?? 0 }))
}

/**
 * The chart for one column. Groups and scale come from `domainRows` (the whole dataset);
 * counts come from `rows` (what has arrived so far). Null when the column has no useful chart.
 */
export function chartFor(column: Column, rows: Row[], domainRows: Row[] = rows): ChartSpec | null {
  const all = valuesOf(domainRows, column.key)
  const b = bucketing(column, all)
  if (!b || b.buckets.length < 2) return null
  const shown = valuesOf(rows, column.key)
  return {
    kind: b.kind,
    column,
    title: b.title,
    reason: b.reason,
    data: count(b, shown),
    counted: shown.length,
    missing: rows.length - shown.length,
    max: Math.max(1, ...count(b, all).map((d) => d.value)),
  }
}

const PRIORITY: Record<string, number> = { date: 0, category: 1, money: 2, number: 3, location: 4 }

/** Up to four charts for a dataset, chosen by column type. */
export function autoCharts(dataset: Dataset, limit = 4): ChartSpec[] {
  return dataset.columns
    .filter((c) => c.type in PRIORITY)
    .sort((a, b) => PRIORITY[a.type] - PRIORITY[b.type])
    .map((c) => chartFor(c, dataset.rows))
    .filter((s): s is ChartSpec => s !== null)
    .slice(0, limit)
}
