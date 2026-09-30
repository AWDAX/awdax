import { OTHER_KEY } from '../../../analytics/aggregate.ts'
import type { QueryResult } from '../../../analytics/aggregate.ts'
import { fromString, toNumber } from '../../../analytics/decimal.ts'
import type { Dec } from '../../../analytics/decimal.ts'
import { formatCompact, formatDec, formatFor } from '../../../analytics/format.ts'
import type { TableProfile } from '../../../analytics/profile.ts'

/** Round tick steps (1, 2, 2.5, 5 × 10^k) covering [min, max], always including 0. Floats: geometry only. */
export function niceTicks(minV: number, maxV: number, count = 4): number[] {
  const lo = Math.min(0, minV)
  const hi = Math.max(0, maxV)
  if (hi === lo) return [0, hi || 1]
  const raw = (hi - lo) / count
  const exp = 10 ** Math.floor(Math.log10(raw))
  const f = raw / exp
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * exp
  const out: number[] = []
  for (let t = Math.floor(lo / step) * step; t <= hi + step * 0.5; t += step) out.push(Number(t.toPrecision(12)))
  if (out[out.length - 1] < hi) out.push(Number((out[out.length - 1] + step).toPrecision(12)))
  return out
}

export interface Formatters {
  /** The exact value, with currency, percent or unit: tooltips, labels, tables. */
  exact: (d: Dec | null) => string
  /** Short axis label for a tick; 	op (the axis's largest tick) keeps one unit along the axis. */
  tick: (t: number, top?: number) => string
}

/** Formatting for a result's values: counts are plain; measures carry their column's unit. */
export function formattersFor(p: TableProfile, r: QueryResult): Formatters {
  const counting = r.query.agg === 'count' || r.query.agg === 'distinct' || r.query.measure === undefined
  const col = counting ? undefined : p.columns[r.query.measure!]
  const opts = { currency: col?.currency, percent: col?.percent }
  return {
    exact: (d) => (counting ? formatDec(d) : formatFor(col, d, r.scale)),
    tick: (t, top) => {
      const dec = (x: number) => fromString(String(x)) ?? fromString(x.toFixed(6))
      const d = dec(t)
      return d ? formatCompact(d, opts, top !== undefined ? dec(Math.abs(top)) ?? undefined : undefined) : String(t)
    },
  }
}

export const num = (d: Dec | null) => (d ? toNumber(d) : 0)

/** Chart data: result rows with a value, as floats for drawing plus the exact value for text. */
export function series(r: QueryResult) {
  return r.rows.filter((x) => x.value !== null).map((x) => ({ key: x.key, label: x.label, value: x.value!, v: num(x.value), count: x.count }))
}

export type Datum = ReturnType<typeof series>[number]

/** Geist Mono at the micro size (12px) with its 0.06em tracking: about 8px a character. */
const CHAR_PX = 8

/**
 * Which labels fit along an axis without touching. Each label's extent follows its anchor: with `ends`, the
 * first is drawn rightwards from its point (text-anchor start) and the last leftwards (end); the rest are
 * centred. Keeps the first, then each one at least `pad` clear of the last kept, and always the last
 * (dropping the kept ones before it that it would touch).
 */
export function spaced(xs: number[], texts: string[], pad = 14, ends = false): Set<number> {
  const n = xs.length
  const span = (i: number): [number, number] => {
    const w = texts[i].length * CHAR_PX
    if (ends && n > 1 && i === 0) return [xs[i], xs[i] + w]
    if (ends && n > 1 && i === n - 1) return [xs[i] - w, xs[i]]
    return [xs[i] - w / 2, xs[i] + w / 2]
  }
  const clear = (a: number, b: number) => span(b)[0] - span(a)[1] >= pad
  const keep: number[] = []
  xs.forEach((_, i) => {
    const last = keep[keep.length - 1]
    if (last === undefined || clear(last, i)) keep.push(i)
  })
  const end = n - 1
  if (end > 0 && keep[keep.length - 1] !== end) {
    while (keep.length > 1 && !clear(keep[keep.length - 1], end)) keep.pop()
    keep.push(end)
  }
  return new Set(keep)
}

/** Y-axis ticks that stay at least `minGap` px apart on a plot `plotH` tall: fewer ticks on a short chart. */
export function ticksFor(minV: number, maxV: number, plotH: number, minGap = 24): number[] {
  for (let count = 4; count > 1; count -= 1) {
    const ticks = niceTicks(minV, maxV, count)
    if (plotH / Math.max(1, ticks.length - 1) >= minGap) return ticks
  }
  return niceTicks(minV, maxV, 1)
}

/** A text halo in the surface colour, so a value label stays readable where it crosses a gridline or a line. */
export const HALO = { stroke: 'var(--color-surface)', strokeWidth: 4, strokeLinejoin: 'round', paintOrder: 'stroke' } as const

/** Bar fill: ink, 'Other' in light grey; with a cross-filter, picked bars go signal yellow and the rest fade. */
export function barTone(key: string, selected?: Set<string>) {
  if (selected && selected.size > 0) return selected.has(key) ? 'fill-signal stroke-ink' : 'fill-line-strong'
  return key === OTHER_KEY ? 'fill-other' : 'fill-series'
}
