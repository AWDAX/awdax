import { filterRows, runQuery } from '../../analytics/aggregate.ts'
import type { Filter } from '../../analytics/aggregate.ts'
import type { Answer } from '../../analytics/answer.ts'
import { toString } from '../../analytics/decimal.ts'
import type { Dec } from '../../analytics/decimal.ts'
import { isNumeric } from '../../analytics/profile.ts'
import type { ColumnProfile, TableProfile } from '../../analytics/profile.ts'
import type { ChartSpec } from '../../analytics/spec.ts'
import { measureTitle } from '../../analytics/suggest.ts'

/** What to export: rows (all or filtered), one chart's numbers, or one answer's numbers. */
export type ExportScope =
  | { kind: 'rows'; filters: Filter[]; label: string }
  | { kind: 'chart'; spec: ChartSpec; filters: Filter[]; label: string }
  | { kind: 'answer'; answer: Answer; label: string }

export type SheetType = 'integer' | 'decimal' | 'date' | 'text'

export interface SheetColumn {
  name: string
  type: SheetType
  /** Decimal columns: digits after the point and total digits, for exact SQL DECIMAL(p, s). */
  scale: number
  precision: number
  /** "INR", "%", "km": said in the header, never mixed into the value. */
  unit?: string
}

/** A value ready for any format: exact decimal string, ISO date, text, or null (missing, never 0). */
export type SheetValue = string | null

export interface Sheet {
  columns: SheetColumn[]
  rows: SheetValue[][]
  /** The scraped text of every cell, for "as scraped" exports. */
  raw: string[][]
}

function unitOf(c: ColumnProfile): string | undefined {
  return c.currency ?? (c.percent ? '%' : c.suffix)
}

function digits(d: Dec): number {
  return (d.n < 0n ? -d.n : d.n).toString().length
}

function numericColumn(name: string, values: (Dec | null)[], unit?: string): SheetColumn {
  const present = values.filter((v): v is Dec => v !== null)
  const scale = Math.max(0, ...present.map((v) => v.s))
  const intDigits = Math.max(1, ...present.map((v) => digits(v) - v.s))
  const precision = Math.min(38, intDigits + scale)
  return { name, type: scale === 0 && intDigits <= 18 ? 'integer' : 'decimal', scale, precision, unit }
}

/** A period as a date where it is one (day → 2024-01-14, month → 2024-01-01), else its label as text. */
function periodValue(c: ColumnProfile, row: number): SheetValue {
  const p = c.periods?.[row]
  if (!p) return null
  if (p.grain === 'day') return p.key
  if (p.grain === 'month') return `${p.key}-01`
  if (p.grain === 'year') return p.key
  return p.label
}

function rowsSheet(p: TableProfile, filters: Filter[]): Sheet {
  const idx = filterRows(p, filters)
  const cols = p.columns.filter((c) => !c.virtual)
  const columns: SheetColumn[] = cols.map((c) => {
    if (isNumeric(c)) return numericColumn(c.name, idx.map((r) => c.numbers![r]), unitOf(c))
    if (c.kind === 'period') {
      const type: SheetType = c.grain === 'day' || c.grain === 'month' ? 'date' : c.grain === 'year' ? 'integer' : 'text'
      return { name: c.name, type, scale: 0, precision: 4 }
    }
    return { name: c.name, type: 'text', scale: 0, precision: 0 }
  })
  const rows = idx.map((r) =>
    cols.map((c) => {
      if (isNumeric(c)) {
        const v = c.numbers![r]
        return v ? toString(v) : null
      }
      if (c.kind === 'period') return periodValue(c, r)
      const t = c.labels[r]
      return t === '' ? null : t
    }),
  )
  return { columns, rows, raw: idx.map((r) => cols.map((c) => c.labels[r])) }
}

function resultSheet(p: TableProfile, spec: { query: ChartSpec['query'] }, filters: Filter[]): Sheet {
  const r = runQuery(p, { ...spec.query, filters: [...(spec.query.filters ?? []), ...filters] })
  const group = r.query.groupBy !== undefined ? p.columns[r.query.groupBy] : undefined
  const measure = r.query.measure !== undefined ? p.columns[r.query.measure] : undefined
  const counting = r.query.agg === 'count' || r.query.agg === 'distinct' || !measure
  const valueName = measureTitle(p, r.query)
  const valueCol = numericColumn(valueName, r.rows.map((x) => x.value), counting ? undefined : measure && unitOf(measure))
  const columns: SheetColumn[] = [
    ...(group ? [{ name: group.label, type: 'text' as const, scale: 0, precision: 0 }] : []),
    valueCol,
    { name: 'Rows', type: 'integer', scale: 0, precision: 10 },
  ]
  const rows = r.rows.map((x) => [...(group ? [x.label] : []), x.value ? toString(x.value) : null, String(x.count)])
  return { columns, rows, raw: rows.map((row) => row.map((v) => v ?? '')) }
}

export function buildSheet(p: TableProfile, scope: ExportScope): Sheet {
  if (scope.kind === 'rows') return rowsSheet(p, scope.filters)
  if (scope.kind === 'chart') return resultSheet(p, scope.spec, scope.filters)
  return resultSheet(p, { query: scope.answer.query }, [])
}

/** "EV sales, Mar 2025" → "ev-sales-mar-2025_2026-09-27" */
export function fileBase(title: string, label: string): string {
  const slug = `${title} ${label === 'All rows' ? '' : label}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'awdax'
  // The viewer's local date: just after midnight in India the UTC date is still yesterday.
  const now = new Date()
  const day = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
  return `${slug}_${day}`
}
