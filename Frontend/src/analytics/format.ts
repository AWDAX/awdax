import { abs, cmp, div, fromInt, round, toString } from './decimal.ts'
import type { Dec } from './decimal.ts'
import type { Currency } from './parse.ts'
import type { ColumnProfile } from './profile.ts'

/**
 * Exact number formatting, straight from the decimal string: no float on the way, so what's printed is
 * what was computed. Indian digit grouping (12,34,567) for rupees and plain numbers; Western grouping
 * (1,234,567) for dollars, euros and pounds.
 */
const SYMBOL: Record<Currency, string> = { INR: '₹', USD: '$', EUR: '€', GBP: '£' }

function group(int: string, indian: boolean): string {
  if (int.length <= 3) return int
  if (!indian) return int.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const last3 = int.slice(-3)
  const rest = int.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ',')
  return `${rest},${last3}`
}

export interface FormatOptions {
  currency?: Currency
  percent?: boolean
  suffix?: string
  /** Round to at most this many decimals (half-to-even). Unset keeps every decimal. */
  maxScale?: number
}

export function formatDec(d: Dec | null, opts: FormatOptions = {}): string {
  if (d === null) return '—'
  const v = opts.maxScale === undefined ? d : round(d, opts.maxScale)
  const s = toString(abs(v))
  const [int, frac] = s.split('.')
  const indian = !opts.currency || opts.currency === 'INR'
  const body = group(int, indian) + (frac ? `.${frac}` : '')
  const sign = v.n < 0n ? '−' : ''
  const sym = opts.currency ? SYMBOL[opts.currency] : ''
  const pct = opts.percent ? '%' : ''
  const unit = opts.suffix ? ` ${opts.suffix}` : ''
  return `${sign}${sym}${body}${pct}${unit}`
}

/** A column's value, formatted with its currency, percent sign or unit. */
export function formatFor(col: ColumnProfile | undefined, d: Dec | null, maxScale?: number): string {
  return formatDec(d, { currency: col?.currency, percent: col?.percent, suffix: col?.suffix, maxScale })
}

const INDIAN_STEPS: [number, string][] = [
  [7, 'Cr'],
  [5, 'L'],
  [3, 'K'],
]
const WESTERN_STEPS: [number, string][] = [
  [9, 'B'],
  [6, 'M'],
  [3, 'K'],
]

/**
 * Short labels for axes only ("1.4 Cr", "250K"); tooltips and tables always use the exact value. Pass the
 * axis's largest tick as `scaleFrom` so every label on one axis uses the same unit (0.5L, 1L, 1.5L, not 50K, 1L).
 */
export function formatCompact(d: Dec, opts: FormatOptions = {}, scaleFrom?: Dec): string {
  const indian = !opts.currency || opts.currency === 'INR'
  for (const [exp, word] of indian ? INDIAN_STEPS : WESTERN_STEPS) {
    const unit = fromInt(10n ** BigInt(exp))
    if (cmp(abs(scaleFrom ?? d), unit) >= 0) {
      if (d.n === 0n) return formatDec(d, { ...opts, suffix: undefined })
      const scaled = div(d, unit, 2)!
      return formatDec(scaled, { ...opts, suffix: undefined }).replace(/(\.0)?(%?)$/, `${word}$2`)
    }
  }
  return formatDec(d, { ...opts, suffix: undefined, maxScale: 2 })
}

/** "12 rows", "1 row" */
export const plural = (n: number, word: string, many = `${word}s`) => `${n.toLocaleString('en-IN')} ${n === 1 ? word : many}`
