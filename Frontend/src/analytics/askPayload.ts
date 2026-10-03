import { AGG_LABEL, columnsExist, filterColumnsExist } from './aggregate.ts'
import type { Filter, Query } from './aggregate.ts'
import { toNumber } from './decimal.ts'
import { groupKey } from './profile.ts'
import type { ColumnProfile, TableProfile } from './profile.ts'
import type { ChartType } from './spec.ts'
import type { Intent } from './suggest.ts'

/** What the AI planner sees of one column. `key` names it in the rows sent for a calculation. */
export interface AskColumn {
  index: number
  key: string
  label: string
  kind: ColumnProfile['kind']
  unit: string
}

const unitOf = (c: ColumnProfile) => (c.currency ? c.currency : c.percent ? '%' : (c.suffix ?? ''))

/** The table as the planner reads it: readable columns, and rows of numbers (exact values as JS numbers) or text. */
export function askPayload(p: TableProfile): { columns: AskColumn[]; rows: Record<string, string | number | null>[] } {
  const used = new Set<string>()
  const columns = p.columns
    .filter((c) => c.kind !== 'empty')
    .map((c) => {
      const base = c.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || `col${c.index}`
      let key = base
      for (let n = 2; used.has(key); n++) key = `${base}_${n}`
      used.add(key)
      return { index: c.index, key, label: c.label, kind: c.kind, unit: unitOf(c) }
    })
  const rows = Array.from({ length: p.rowCount }, (_, r) => {
    const row: Record<string, string | number | null> = {}
    for (const a of columns) {
      const c = p.columns[a.index]
      if (c.numbers) row[a.key] = c.numbers[r] ? toNumber(c.numbers[r]!) : null
      else if (c.periods) row[a.key] = c.periods[r]?.label ?? null
      else row[a.key] = c.labels[r] || null
    }
    return row
  })
  return { columns, rows }
}

/**
 * The planner's query in the engine's terms, or null when it doesn't fit this table (the second guardrail, after
 * the server's). "In" values arrive as written in the cells ("Tata", "2024") and become the engine's group keys.
 */
export function toEngineQuery(p: TableProfile, q: Query): Query | null {
  if (typeof q?.agg !== 'string' || !(q.agg in AGG_LABEL)) return null
  const filters: Filter[] = []
  for (const f of q.filters ?? []) {
    const col = p.columns[f.column]
    if ((f.op === 'in' || f.op === 'notIn') && col) {
      if (col.kind === 'period') {
        const years = f.values.every((v) => /^\d{4}$/.test(String(v).trim()))
        const byLabel = new Map((col.periods ?? []).filter(Boolean).map((x) => [x!.label.toLowerCase(), x!.key]))
        // A year on a column with no years ("Month": January…) would match nothing: use a date column that has them.
        const hasYears = (c: ColumnProfile) => (c.periods ?? []).some((x) => x?.year !== undefined)
        const target = years && !hasYears(col) ? (p.columns.find((c) => c.kind === 'period' && hasYears(c)) ?? col) : col
        filters.push(years ? { ...f, column: target.index, values: f.values.map((v) => String(v).trim()), bucket: 'year' } : { ...f, values: f.values.map((v) => byLabel.get(String(v).toLowerCase()) ?? String(v)) })
      } else {
        filters.push({ ...f, values: f.values.map((v) => groupKey(String(v))) })
      }
    } else {
      filters.push(f)
    }
  }
  const out: Query = { ...q, filters }
  return columnsExist(p, out) && filterColumnsExist(p, filters) ? out : null
}

/** How an AI-planned query is worded and drawn, read from its shape. */
export function presentQuery(p: TableProfile, q: Query): { intent: Intent; chart: ChartType } {
  const group = q.groupBy !== undefined ? p.columns[q.groupBy] : undefined
  const intent: Intent =
    q.sort === 'value-desc' && q.limit ? 'top' : q.sort === 'value-asc' && q.limit ? 'bottom' : q.agg === 'avg' ? 'average' : q.agg === 'count' ? 'count' : group?.kind === 'period' ? 'trend' : 'total'
  const chart: ChartType = !group ? 'kpi' : group.kind === 'period' ? 'line' : 'bar'
  return { intent, chart }
}
