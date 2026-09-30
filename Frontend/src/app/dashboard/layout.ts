import type { ChartSpec, ChartType } from '../../analytics/spec.ts'

/** One tile on the page: w in columns (2–12), h in page rows (1–6). */
export interface Tile {
  spec: ChartSpec
  w: number
  h: number
}

/** A report page, like Power BI's: 12 columns × 6 rows, sized to fit one screen. */
export const PAGE_COLS = 12
export const PAGE_ROWS = 6

const SIZE: Record<ChartType, [number, number]> = {
  kpi: [3, 1],
  line: [6, 3],
  area: [6, 3],
  column: [6, 3],
  bar: [6, 3],
  pie: [6, 3],
  donut: [6, 3],
  scatter: [6, 3],
  table: [12, 3],
}
export const sizeFor = (type: ChartType) => SIZE[type]
export const clampW = (w: number) => Math.max(2, Math.min(PAGE_COLS, Math.round(w)))
export const clampH = (h: number) => Math.max(1, Math.min(PAGE_ROWS, Math.round(h)))

/** Widths for k charts sharing a row; the first (usually the trend) gets the most room. */
const WIDTHS: Record<number, number[]> = { 1: [12], 2: [7, 5], 3: [4, 4, 4] }

/**
 * Lays specs out as one page: number cards share the top row, then charts fill two rows (up to three per row).
 * Anything past six charts goes below the page, at a readable size.
 */
export function layoutPage(specs: ChartSpec[]): Tile[] {
  const kpis = specs.filter((s) => s.type === 'kpi').slice(0, 4)
  const extraKpis = specs.filter((s) => s.type === 'kpi').slice(4)
  const charts = specs.filter((s) => s.type !== 'kpi')
  const out: Tile[] = kpis.map((spec) => ({ spec, w: PAGE_COLS / kpis.length, h: 1 }))
  const rowsLeft = PAGE_ROWS - (kpis.length ? 1 : 0)
  const onPage = charts.slice(0, 6)
  const topCount = onPage.length <= 1 ? onPage.length : Math.ceil(onPage.length / 2)
  const rows = [onPage.slice(0, topCount), onPage.slice(topCount)].filter((r) => r.length)
  const heights = rows.length === 1 ? [rowsLeft] : [Math.ceil(rowsLeft / 2), Math.floor(rowsLeft / 2)]
  rows.forEach((row, ri) => row.forEach((spec, i) => out.push({ spec, w: WIDTHS[row.length][i], h: heights[ri] })))
  for (const spec of [...charts.slice(6), ...extraKpis]) {
    const [w, h] = SIZE[spec.type]
    out.push({ spec, w, h })
  }
  return out
}

/**
 * How many rows the tiles take when the grid packs them densely (CSS grid-auto-flow: row dense), so the
 * dashboard can say when something has spilled below the page.
 */
export function packedRows(tiles: { w: number; h: number }[], cols = PAGE_COLS): number {
  const grid: boolean[][] = []
  const free = (r: number, c: number, w: number, h: number) => {
    for (let y = r; y < r + h; y++) for (let x = c; x < c + w; x++) if (grid[y]?.[x]) return false
    return true
  }
  let bottom = 0
  for (const t of tiles) {
    const w = Math.min(cols, t.w)
    let placed = false
    for (let r = 0; !placed; r++) {
      for (let c = 0; c + w <= cols && !placed; c++) {
        if (!free(r, c, w, t.h)) continue
        for (let y = r; y < r + t.h; y++) {
          grid[y] ??= []
          for (let x = c; x < c + w; x++) grid[y][x] = true
        }
        bottom = Math.max(bottom, r + t.h)
        placed = true
      }
    }
  }
  return bottom
}
