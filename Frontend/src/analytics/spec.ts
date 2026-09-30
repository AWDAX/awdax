import type { Query } from './aggregate.ts'

export type ChartType = 'column' | 'bar' | 'line' | 'area' | 'pie' | 'donut' | 'scatter' | 'kpi' | 'table'

/** One dashboard tile: what to draw and the exact query behind it. Stored per chat, so keep it JSON-safe. */
export interface ChartSpec {
  id: string
  type: ChartType
  title: string
  /** One sentence saying why this chart fits the data (DESIGN_SYSTEM "Charts"). */
  reason: string
  query: Query
  /** Scatter only: the two numeric columns. */
  x?: number
  y?: number
  /** Print each value on its mark. */
  labels?: boolean
  /** The chart's one colour (tokens.css `chart-*`). Unset means ink. */
  color?: ChartColor
}

export type ChartColor = 'ink' | 'blue' | 'teal' | 'green' | 'orange' | 'purple' | 'pink'

export const CHART_LABEL: Record<ChartType, string> = {
  column: 'Column',
  bar: 'Bar',
  line: 'Line',
  area: 'Area',
  pie: 'Pie',
  donut: 'Donut',
  scatter: 'Scatter',
  kpi: 'Number card',
  table: 'Table',
}

/** Which chart types make sense for a query's shape. */
export function typesFor(hasGroup: boolean, groupIsTime: boolean): ChartType[] {
  if (!hasGroup) return ['kpi', 'table']
  if (groupIsTime) return ['line', 'area', 'column', 'bar', 'table']
  return ['bar', 'column', 'pie', 'donut', 'line', 'table']
}

let seq = 0
export const newId = (prefix = 'c') => `${prefix}${Date.now().toString(36)}${(seq++).toString(36)}`
