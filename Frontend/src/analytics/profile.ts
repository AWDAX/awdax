import type { DatasetTable } from '../api/types.ts'
import type { Dec } from './decimal.ts'
import { isMissingText, isUrl, parseDuration, parseNumber } from './parse.ts'
import type { Currency } from './parse.ts'
import { combineMonthYear, parsePeriod } from './period.ts'
import type { Grain, Period } from './period.ts'

export type ColumnKind = 'number' | 'money' | 'percent' | 'period' | 'category' | 'url' | 'text' | 'empty'

/** A non-empty cell that couldn't be read as its column's kind, and why. It's left out of every number. */
export interface Excluded {
  row: number
  raw: string
  reason: string
}

export interface ColumnProfile {
  index: number
  /** The header as scraped. */
  name: string
  /** The header made readable: "price_inr" → "Price inr". */
  label: string
  kind: ColumnKind
  filled: number
  missing: number
  /** Distinct values, ignoring case and extra spaces. */
  distinct: number
  /** One entry per row: the trimmed text, or '' when missing. */
  labels: string[]
  /** Numeric kinds: one exact value per row, null when missing or excluded. */
  numbers?: (Dec | null)[]
  /** Period kind: one period per row. */
  periods?: (Period | null)[]
  excluded: Excluded[]
  currency?: Currency
  percent?: boolean
  /** A shared trailing unit ("km", "units"). */
  suffix?: string
  /** Most decimals seen in a value, so answers show the same precision as the source. */
  scale: number
  grain?: Grain
  /** Slashed dates where day and month could be either way round (read as day/month). */
  ambiguous?: number
  /** Serial numbers or ranks: numeric, but never a measure worth adding up. */
  idLike?: boolean
  /** Built by the profile (Month + Year), not in the scraped table; exports leave it out. */
  virtual?: boolean
}

export interface TableProfile {
  columns: ColumnProfile[]
  rowCount: number
  /** Rows as text, exactly as scraped. */
  raw: string[][]
  name?: string
  sourceUrl?: string
}

const cellText = (v: string | number | null | undefined) => (v === null || v === undefined ? '' : String(v).trim())
export const groupKey = (label: string) => label.replace(/\s+/g, ' ').trim().toLowerCase()

const CODES = new Set(['inr', 'usd', 'eur', 'gbp'])
const UNITS = new Set(['km', 'kg', 'kwh', 'kw', 'hp', 'cc', 'mm', 'cm', 'm', 'sqft', 'hrs', 'mins', 'mah', 'gb', 'tb', 'pct'])

/** "price_inr" → "Price (INR)", "range_km" → "Range (km)", "EV Units Sold" stays as it is. */
export function humanize(name: string): string {
  const words = name.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim().split(' ')
  const last = words[words.length - 1]?.toLowerCase() ?? ''
  if (words.length > 1 && (CODES.has(last) || UNITS.has(last))) {
    words[words.length - 1] = `(${CODES.has(last) ? last.toUpperCase() : last === 'pct' ? '%' : last})`
  }
  const s = words.join(' ')
  return s ? s[0].toUpperCase() + s.slice(1) : 'Column'
}

/** A label for mid-sentence use: "Price (INR)" → "price (INR)", but "EV units" keeps its capitals. */
export const lc = (label: string) => (/^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label)

function mostCommon<T>(items: T[]): T | undefined {
  const counts = new Map<T, number>()
  for (const i of items) counts.set(i, (counts.get(i) ?? 0) + 1)
  let best: T | undefined
  let bestN = 0
  for (const [k, n] of counts) if (n > bestN) [best, bestN] = [k, n]
  return best
}

const ID_NAME = /(^|\b|_)(id|no|sr|s\.?no|serial|rank|index|#)(\b|_|$)/i
const TIME_NAME = /date|month|period|quarter|time|day|year|\bfy\b|week/i
const CATEGORY_NAME = /segment|type|class|category|variant|grade|tier|size|model|code/i
const MEASURE_NAME = /price|cost|amount|revenue|sales|range|battery|power|speed|capacity|score|count|qty|quantity|value|volume|percentage|percent|charging.*time|duration/i

function profileColumn(index: number, name: string, cells: string[]): ColumnProfile {
  const base = { index, name, label: humanize(name), labels: cells, excluded: [] as Excluded[], scale: 0 }
  const present = cells.map((c, row) => ({ c, row })).filter(({ c }) => c !== '' && !isMissingText(c))
  const filled = present.length
  const missing = cells.length - filled
  const distinct = new Set(present.map(({ c }) => groupKey(c))).size
  if (filled === 0) return { ...base, kind: 'empty', filled, missing, distinct }

  const durationCount = present.filter(({ c }) => parseDuration(c).ok).length
  const duration = durationCount >= Math.max(1, Math.ceil(filled * 0.8))
    || (/charging.*time|duration/i.test(name) && durationCount >= 2)
  const nums = present.map(({ c, row }) => ({ row, c, r: duration ? parseDuration(c) : parseNumber(c) }))
  const numOk = nums.filter((x) => x.r.ok)
  const pers = present.map(({ c, row }) => ({ row, c, p: parsePeriod(c) }))
  const perOk = pers.filter((x) => x.p !== null)
  const urls = present.filter(({ c }) => isUrl(c)).length
  const enough = (n: number) => n >= Math.max(1, Math.ceil(filled * 0.8))

  if (enough(urls)) return { ...base, kind: 'url', filled, missing, distinct }

  // A column of 4-digit numbers is a year only when its header says so: prices like 1999 must stay numbers.
  const yearLike = enough(perOk.length) && perOk.every((x) => x.p!.grain === 'year') && /year|yr|\bfy\b/i.test(name)
  const timeLike = enough(perOk.length) && (perOk.length > numOk.length || TIME_NAME.test(name))
  if (yearLike || timeLike) {
    const grain = mostCommon(perOk.map((x) => x.p!.grain))!
    const periods: (Period | null)[] = cells.map(() => null)
    const excluded: Excluded[] = []
    for (const x of pers) {
      if (x.p && x.p.grain === grain) periods[x.row] = x.p
      else excluded.push({ row: x.row, raw: x.c, reason: x.p ? `a ${x.p.grain}, not a ${grain}` : 'not a date or period' })
    }
    const ambiguous = perOk.filter((x) => x.p!.ambiguous).length
    return { ...base, kind: 'period', filled, missing, distinct, periods, excluded, grain, ambiguous: ambiguous || undefined }
  }

  // Short codes glued to a unit-like word ("2W", "4W", "5G", "3BHK") that repeat across rows are categories,
  // not quantities: adding up "2W + 4W" would be a precise-looking wrong number. So are columns named like one.
  const codes = present.filter(({ c }) => /^\d{1,2}[a-z]{1,4}$/i.test(c.trim())).length
  const codeLike = (enough(codes) && distinct <= 12 && distinct <= filled * 0.5) || (CATEGORY_NAME.test(name) && distinct <= 20 && distinct <= filled * 0.5)
  const namedMeasure = MEASURE_NAME.test(name) && numOk.length >= 2 && numOk.length >= Math.ceil(filled * 0.2)
  if ((enough(numOk.length) || namedMeasure) && !codeLike) {
    const parsed = numOk.map((x) => (x.r.ok ? x.r.num : null)!)
    const currency = mostCommon(parsed.map((p) => p.currency).filter((c): c is Currency => !!c))
    const moneyVotes = parsed.filter((p) => p.currency).length
    const percent = parsed.filter((p) => p.percent).length * 2 > parsed.length
    const suffix = mostCommon(parsed.map((p) => p.suffix).filter((s): s is string => !!s))
    const numbers: (Dec | null)[] = cells.map(() => null)
    const excluded: Excluded[] = []
    let scale = 0
    for (const x of nums) {
      if (!x.r.ok) {
        excluded.push({ row: x.row, raw: x.c, reason: x.r.reason })
        continue
      }
      const p = x.r.num
      if (p.currency && currency && p.currency !== currency) {
        excluded.push({ row: x.row, raw: x.c, reason: `in ${p.currency}, the column is in ${currency}` })
        continue
      }
      if (p.suffix && suffix && p.suffix !== suffix) {
        excluded.push({ row: x.row, raw: x.c, reason: `in “${p.suffix}”, the column is in “${suffix}”` })
        continue
      }
      numbers[x.row] = p.value
      scale = Math.max(scale, p.value.s)
    }
    const kind: ColumnKind = moneyVotes * 2 > parsed.length ? 'money' : percent ? 'percent' : 'number'
    const ints = numbers.filter((n): n is Dec => n !== null)
    const consecutive = ints.length > 2 && ints.every((d, i) => d.s === 0 && d.n === BigInt(i + 1))
    const idLike = kind === 'number' && (ID_NAME.test(name) || consecutive)
    return {
      ...base, kind, filled, missing, distinct, numbers, excluded, scale,
      currency: kind === 'money' ? currency : undefined,
      percent: kind === 'percent' || undefined,
      suffix, idLike: idLike || undefined,
    }
  }

  const avgLength = present.reduce((n, { c }) => n + c.length, 0) / filled
  const category = distinct >= 1 && avgLength <= 48 && (distinct <= 12 || distinct <= Math.ceil(filled * 0.6))
  return { ...base, kind: category ? 'category' : 'text', filled, missing, distinct }
}

/** A Month column (January…) beside a Year column becomes one real timeline. */
function monthYear(columns: ColumnProfile[], rowCount: number): ColumnProfile | null {
  const monthCol = columns.find((c) => c.kind === 'period' && c.grain === 'monthName')
  const yearCol = columns.find((c) => c.kind === 'period' && c.grain === 'year')
  if (!monthCol || !yearCol) return null
  const periods = Array.from({ length: rowCount }, (_, r) =>
    combineMonthYear(monthCol.periods?.[r] ?? null, yearCol.periods?.[r] ?? null),
  )
  const filled = periods.filter(Boolean).length
  if (filled === 0) return null
  return {
    index: columns.length,
    name: `${monthCol.name} + ${yearCol.name}`,
    label: `${monthCol.label} and ${yearCol.label}`,
    kind: 'period',
    grain: 'month',
    filled,
    missing: rowCount - filled,
    distinct: new Set(periods.filter(Boolean).map((p) => p!.key)).size,
    labels: periods.map((p) => p?.label ?? ''),
    periods,
    excluded: [],
    scale: 0,
    virtual: true,
  }
}

/** Reads a scraped table: what each column holds, every value parsed exactly, every left-out cell listed. */
export function profileTable(table: DatasetTable): TableProfile {
  const raw = table.rows.map((row) => table.columns.map((_, i) => cellText(row[i])))
  const columns = table.columns.map((name, i) => profileColumn(i, name, raw.map((r) => r[i])))
  const combined = monthYear(columns, raw.length)
  if (combined) columns.push(combined)
  return { columns, rowCount: raw.length, raw, name: table.name, sourceUrl: table.source_url }
}

export const isNumeric = (c: ColumnProfile) => c.kind === 'number' || c.kind === 'money' || c.kind === 'percent'
export const isMeasure = (c: ColumnProfile) => isNumeric(c) && !c.idLike
export const isGroupable = (c: ColumnProfile) =>
  c.kind === 'category' || c.kind === 'period' || c.kind === 'url' || (c.kind === 'text' && c.distinct <= 60)
