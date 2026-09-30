import { cmp, fromInt, max, mean, median, min, sum } from './decimal.ts'
import type { Dec } from './decimal.ts'
import { isMissingText, parseNumber } from './parse.ts'
import { bucketOf } from './period.ts'
import type { Bucket } from './period.ts'
import { groupKey } from './profile.ts'
import type { ColumnProfile, Excluded, TableProfile } from './profile.ts'

export type Agg = 'count' | 'sum' | 'avg' | 'min' | 'max' | 'median' | 'distinct'

/** 'search' ignores `column` and matches text in any scraped column of the row. */
export type FilterOp = 'in' | 'notIn' | 'contains' | 'gte' | 'lte' | 'between' | 'present' | 'search'

export interface Filter {
  column: number
  op: FilterOp
  /** 'in'/'notIn': group keys (lower-case labels, or period keys). 'gte'/'lte'/'between': decimal strings. */
  values: string[]
  /** For 'in'/'notIn' on a date column: the keys are months, quarters or years (a cross-filter from a grouped chart). */
  bucket?: Bucket
}

export type SortBy = 'value-desc' | 'value-asc' | 'label' | 'time'

export interface Query {
  /** Column to group by; unset gives one overall row. */
  groupBy?: number
  /** Numeric column to aggregate; unset (or agg 'count') counts rows. */
  measure?: number
  agg: Agg
  filters?: Filter[]
  sort?: SortBy
  /** Keep the first N groups after sorting. */
  limit?: number
  /** Fold the groups past `limit` into one "Other" row. */
  other?: boolean
  /** Group a date column by month, quarter or year instead of by each date. */
  bucket?: Bucket
}

export interface ResultRow {
  key: string
  label: string
  value: Dec | null
  /** Rows that went into this value (after filters and exclusions). */
  count: number
  rows: number[]
}

export interface QueryResult {
  query: Query
  rows: ResultRow[]
  /** The same aggregate over every row used, e.g. the grand total. */
  overall: Dec | null
  /** Rows that passed the filters. */
  matched: number
  /** Rows that passed the filters and had a usable value. */
  used: number
  /** Cells left out of the numbers, with the reason. */
  excluded: (Excluded & { column: string })[]
  /** Rows that passed the filters but had no value (empty or "N/A" in the source) for the group or measure. */
  blank: { row: number; column: string }[]
  /** Decimals to show: the source's precision, plus 2 for averages. */
  scale: number
}

export const OTHER_KEY = '__other'
const AVG_EXTRA = 2

/** "https://www.vahan.example/ev?x=1" → "vahan.example": web addresses group by site. */
export function siteOf(url: string): string {
  const m = /^(?:[a-z][a-z0-9+.-]*:\/\/)?(?:www\.)?([^/?#:\s]+)/i.exec(url.trim())
  return (m?.[1] ?? url).toLowerCase()
}

function valueKey(col: ColumnProfile, row: number, bucket?: Bucket): { key: string; label: string } | null {
  if (col.kind === 'period') {
    const p = col.periods?.[row]
    if (!p) return null
    const b = bucket ? bucketOf(p, bucket) : p
    return { key: b.key, label: b.label }
  }
  const label = col.labels[row]
  if (!label || isMissingText(label)) return null
  if (col.kind === 'url') {
    const site = siteOf(label)
    return { key: site, label: site }
  }
  return { key: groupKey(label), label: label.replace(/\s+/g, ' ') }
}

function passes(p: TableProfile, f: Filter, row: number): boolean {
  if (f.op === 'search') {
    const needle = (f.values[0] ?? '').trim().toLowerCase()
    return !needle || p.raw[row].some((cell) => cell.toLowerCase().includes(needle))
  }
  const col = p.columns[f.column]
  if (!col) return true
  if (f.op === 'present') {
    if (col.numbers) return col.numbers[row] !== null
    if (col.periods) return col.periods[row] !== null
    return col.labels[row] !== '' && !isMissingText(col.labels[row])
  }
  if (f.op === 'contains') return col.labels[row].toLowerCase().includes((f.values[0] ?? '').toLowerCase())
  if (f.op === 'in' || f.op === 'notIn') {
    const k = valueKey(col, row, f.bucket)?.key
    const hit = k !== undefined && f.values.includes(k)
    return f.op === 'in' ? hit : !hit
  }
  const v = col.numbers?.[row]
  if (!v) return false
  const bound = (s: string | undefined) => {
    const r = s === undefined ? null : parseNumber(s)
    return r && r.ok ? r.num.value : null
  }
  const lo = bound(f.values[0])
  const hi = bound(f.op === 'between' ? f.values[1] : f.values[0])
  if (f.op === 'gte') return lo !== null && cmp(v, lo) >= 0
  if (f.op === 'lte') return hi !== null && cmp(v, hi) <= 0
  return lo !== null && hi !== null && cmp(v, lo) >= 0 && cmp(v, hi) <= 0
}

/** Row indexes that pass every filter. */
export function filterRows(p: TableProfile, filters: Filter[] = []): number[] {
  const out: number[] = []
  for (let r = 0; r < p.rowCount; r++) if (filters.every((f) => passes(p, f, r))) out.push(r)
  return out
}

function reduce(agg: Agg, values: Dec[], rows: number, distinctKeys: Set<string>, scale: number): Dec | null {
  switch (agg) {
    case 'count':
      return fromInt(rows)
    case 'distinct':
      return fromInt(distinctKeys.size)
    case 'sum':
      return values.length ? sum(values) : null
    case 'avg':
      return mean(values, scale + AVG_EXTRA)
    case 'median':
      return median(values)
    case 'min':
      return min(values)
    case 'max':
      return max(values)
  }
}

/** Runs one query: filter, group, aggregate, sort, top N. Every number is exact; nothing is guessed. */
export function runQuery(p: TableProfile, q: Query): QueryResult {
  const measure = q.measure !== undefined ? p.columns[q.measure] : undefined
  const group = q.groupBy !== undefined ? p.columns[q.groupBy] : undefined
  const needsValue = q.agg !== 'count' && q.agg !== 'distinct'
  const matched = filterRows(p, q.filters)
  const excluded: QueryResult['excluded'] = []
  const excludedRows = new Set((measure?.excluded ?? []).map((e) => e.row))

  const buckets = new Map<string, { label: string; values: Dec[]; rows: number[]; keys: Set<string> }>()
  const usedRows: number[] = []
  const blank: { row: number; column: string }[] = []
  for (const r of matched) {
    const g = group ? valueKey(group, r, q.bucket) : { key: 'all', label: 'All rows' }
    if (!g) {
      blank.push({ row: r, column: group!.label })
      continue
    }
    let v: Dec | null = null
    if (needsValue) {
      v = measure?.numbers?.[r] ?? null
      if (v === null) {
        if (excludedRows.has(r)) {
          const e = measure!.excluded.find((x) => x.row === r)!
          excluded.push({ ...e, column: measure!.label })
        } else blank.push({ row: r, column: measure!.label })
        continue
      }
    }
    const b = buckets.get(g.key) ?? { label: g.label, values: [], rows: [], keys: new Set<string>() }
    if (v) b.values.push(v)
    b.rows.push(r)
    if (q.agg === 'distinct' && measure) {
      const k = valueKey(measure, r)?.key
      if (k) b.keys.add(k)
    }
    buckets.set(g.key, b)
    usedRows.push(r)
  }

  const scale = measure?.scale ?? 0
  let rows: ResultRow[] = [...buckets.entries()].map(([key, b]) => ({
    key,
    label: b.label,
    value: reduce(q.agg, b.values, b.rows.length, b.keys, scale),
    count: b.rows.length,
    rows: b.rows,
  }))

  const sortBy: SortBy = q.sort ?? (group?.kind === 'period' ? 'time' : 'value-desc')
  const byValue = (a: ResultRow, b: ResultRow) => (a.value && b.value ? cmp(a.value, b.value) : a.value ? 1 : b.value ? -1 : 0)
  if (sortBy === 'time') rows.sort((a, b) => a.key.localeCompare(b.key))
  else if (sortBy === 'label') rows.sort((a, b) => a.label.localeCompare(b.label, 'en', { numeric: true }))
  else rows.sort((a, b) => (sortBy === 'value-desc' ? -1 : 1) * byValue(a, b) || a.label.localeCompare(b.label))

  if (q.limit !== undefined && rows.length > q.limit) {
    const kept = rows.slice(0, q.limit)
    if (q.other) {
      const rest = rows.slice(q.limit)
      const restRows = rest.flatMap((x) => x.rows)
      const restValues = rest.flatMap((x) => (needsValue ? x.rows.map((r) => measure!.numbers![r]!) : []))
      const restKeys = new Set(restRows.map((r) => (measure ? valueKey(measure, r)?.key : undefined)).filter((k): k is string => !!k))
      kept.push({
        key: OTHER_KEY,
        label: `Other (${rest.length})`,
        value: reduce(q.agg, restValues, restRows.length, restKeys, scale),
        count: restRows.length,
        rows: restRows,
      })
    }
    rows = kept
  }

  const allValues = needsValue ? usedRows.map((r) => measure!.numbers![r]!) : []
  const allKeys = new Set(usedRows.map((r) => (measure ? valueKey(measure, r)?.key : undefined)).filter((k): k is string => !!k))
  return {
    query: q,
    rows,
    overall: reduce(q.agg, allValues, usedRows.length, allKeys, scale),
    matched: matched.length,
    used: usedRows.length,
    excluded,
    blank,
    scale: q.agg === 'avg' ? scale + AVG_EXTRA : scale,
  }
}

/** Paired numeric values for a scatter plot, with the rows that lacked either one. */
export function points(p: TableProfile, x: number, y: number, filters: Filter[] = []) {
  const cx = p.columns[x]
  const cy = p.columns[y]
  const out: { row: number; x: Dec; y: Dec }[] = []
  let skipped = 0
  for (const r of filterRows(p, filters)) {
    const a = cx?.numbers?.[r]
    const b = cy?.numbers?.[r]
    if (a && b) out.push({ row: r, x: a, y: b })
    else skipped++
  }
  return { points: out, skipped }
}

export const AGG_LABEL: Record<Agg, string> = {
  count: 'Count of rows',
  sum: 'Sum',
  avg: 'Average',
  min: 'Minimum',
  max: 'Maximum',
  median: 'Median',
  distinct: 'Distinct count',
}
