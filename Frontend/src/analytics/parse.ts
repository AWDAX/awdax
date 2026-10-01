import { add, cmp, div, fromInt, fromString, mul, neg, shift } from './decimal.ts'
import type { Dec } from './decimal.ts'

/**
 * Scraped cells are strings ("₹12.5 lakh", "1,44,879", "(1,200)", "18.4%", "450 km", "₹11.45 - ₹26.95 Lakh*").
 * This reads them into exact decimals and says what it read, normalizing ranges to midpoints and cleaning
 * trailing footnotes/asterisks, so dynamic scraped data remains fully usable in aggregations.
 * A missing value ("N/A", "—") is never read as 0.
 */

export type Currency = 'INR' | 'USD' | 'EUR' | 'GBP'

export interface ParsedNumber {
  value: Dec
  currency?: Currency
  percent?: boolean
  /** A trailing unit such as "km", "kWh", "units", normalised to lower case. */
  suffix?: string
  /** The scale word that was applied: "lakh" turns 12.5 into 1250000. */
  scaleWord?: string
  /** The power-of-10 shift applied for this scale (5 for lakh, 7 for crore). */
  scaleShift?: number
  /** Marked "~", "approx." or "about" in the source, or a normalized range midpoint. */
  approx?: boolean
  /** The original bounds when parsed from a range. */
  range?: { min: Dec; max: Dec }
  /** True when value represents the normalized midpoint of a range. */
  isRangeMidpoint?: boolean
}

export type NumberRead = { ok: true; num: ParsedNumber } | { ok: false; missing: boolean; reason: string }

/** Read a duration into minutes so mixed hour/minute cells share one honest axis. */
export function parseDuration(input: string): NumberRead {
  const match = /^(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?)(?:\s+(\d+(?:\.\d+)?)\s*(minutes?|mins?))?$/i.exec(input.trim())
  if (!match) return { ok: false, missing: false, reason: 'not a duration' }
  const first = fromString(match[1])!
  const second = match[3] ? fromString(match[3])! : fromInt(0)
  const hours = /^(?:hours?|hrs?|h)$/i.test(match[2])
  if (!hours && match[3]) return { ok: false, missing: false, reason: 'minutes followed by another duration' }
  return { ok: true, num: { value: add(hours ? mul(first, fromInt(60)) : first, second), suffix: 'min' } }
}

const MISSING = new Set([
  '', '-', '--', '—', '–', '_', '?', 'n/a', 'na', 'n.a.', 'nan', 'null', 'none', 'nil', 'not found',
  'not available', 'unknown', 'tbd', 'tba', 'not disclosed', 'undisclosed', '#n/a', 'nd',
])

export function isMissingText(raw: string): boolean {
  return MISSING.has(raw.trim().toLowerCase().replace(/\s+/g, ' '))
}

const CURRENCIES: [RegExp, Currency][] = [
  [/₹|\brs\.?|\binr\b/i, 'INR'],
  [/us\$|\busd\b|\$/i, 'USD'],
  [/€|\beur\b/i, 'EUR'],
  [/£|\bgbp\b/i, 'GBP'],
]

// Longest first, so "lakhs" wins over "l" and "mn" over "m".
const SCALES: [RegExp, number, string][] = [
  [/^(crores?|cr)\.?$/i, 7, 'crore'],
  [/^(lakhs?|lacs?|lakh|l)\.?$/i, 5, 'lakh'],
  [/^(billions?|bn|b)\.?$/i, 9, 'billion'],
  [/^(millions?|mn|mil|m)\.?$/i, 6, 'million'],
  [/^(thousands?|k)\.?$/i, 3, 'thousand'],
]

// Digits with optional grouping, Western (1,234,567), Indian (12,34,567) or spaced (1 234 567).
const GROUPED = /^(\d{1,3}(?:,\d{2,3})+|\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(\.\d+)?$/

function readDigits(body: string): Dec | null {
  const m = GROUPED.exec(body)
  if (!m) {
    const bare = /^\.(\d+)$/.exec(body)
    return bare ? fromString(`0.${bare[1]}`) : null
  }
  const whole = m[1]
  // Grouped numbers: only the last group must be 3 digits; Indian groups before it are 2.
  if (whole.includes(',')) {
    const groups = whole.split(',')
    if (groups[groups.length - 1].length !== 3) return null
  }
  return fromString(whole.replace(/[, \u00a0\u202f]/g, '') + (m[2] ?? ''))
}

/** Reads a single numeric value with its currency, scale, percentage or unit. */
export function parseSingleNumber(rawText: string): NumberRead {
  let s = rawText.trim()
  if (isMissingText(s)) return { ok: false, missing: true, reason: 'marked as missing' }
  const num: Partial<ParsedNumber> = {}

  if (/^(~|≈|approx\.?|about|around|circa|ca\.)\s*/i.test(s)) {
    num.approx = true
    s = s.replace(/^(~|≈|approx\.?|about|around|circa|ca\.)\s*/i, '')
  }

  let negative = false
  const paren = /^\((.*)\)$/.exec(s)
  if (paren) {
    negative = true
    s = paren[1].trim()
  }
  for (const [re, code] of CURRENCIES) {
    if (re.test(s)) {
      num.currency = code
      s = s.replace(re, ' ').trim()
      break
    }
  }
  if (/^[-−]/.test(s)) {
    negative = !negative
    s = s.slice(1).trim()
  } else if (s.startsWith('+')) {
    s = s.slice(1).trim()
  }
  if (s.endsWith('%')) {
    num.percent = true
    s = s.slice(0, -1).trim()
  }

  const m = /^([\d.,\s\u00a0\u202f]*\d)\s*(.*)$/.exec(s) ?? /^(\.\d+)\s*(.*)$/.exec(s)
  if (!m) return { ok: false, missing: false, reason: 'no number in the text' }
  let value = readDigits(m[1].trim())
  if (!value) return { ok: false, missing: false, reason: 'digits are grouped oddly' }

  let rest = m[2].trim().replace(/^[/]-$/, '')
  if (rest.endsWith('%') && !num.percent) {
    num.percent = true
    rest = rest.slice(0, -1).trim()
  }
  const [first, ...more] = rest.split(/\s+/).filter(Boolean)
  const scale = first ? SCALES.find(([re]) => re.test(first)) : undefined
  if (scale) {
    value = shift(value, scale[1])
    num.scaleWord = scale[2]
    num.scaleShift = scale[1]
    rest = more.join(' ')
  }
  if (rest) {
    // A short unit ("km", "kWh", "units/month", "sq ft") is fine; a sentence is not a number.
    if (!/^[a-z][a-z0-9 ./²³-]{0,15}$/i.test(rest) || /\d{2,}/.test(rest)) {
      return { ok: false, missing: false, reason: 'text around the number' }
    }
    num.suffix = rest.toLowerCase().replace(/\.$/, '')
  }
  return { ok: true, num: { ...num, value: negative ? neg(value) : value } }
}

/**
 * Reads one cell as a number or normalizes a numeric range to its representative midpoint.
 * Cleans scraped noise such as trailing asterisks, footnotes (*, #), and currency notations.
 */
export function parseNumber(input: string | number | null | undefined): NumberRead {
  if (input === null || input === undefined) return { ok: false, missing: true, reason: 'empty' }
  if (typeof input === 'number') {
    if (!Number.isFinite(input)) return { ok: false, missing: false, reason: 'not a finite number' }
    const d = fromString(String(input))
    return d ? { ok: true, num: { value: d } } : { ok: false, missing: false, reason: 'not a number' }
  }
  let s = input.trim()
  if (isMissingText(s)) return { ok: false, missing: true, reason: 'marked as missing' }

  // Clean trailing footnotes, asterisks, and currency suffixes (e.g. "₹79.60 Lakh*", "Rs. 5,000/-")
  s = s.replace(/\s*\/-$/, '').replace(/[*#†‡]/g, '').trim()

  // Dynamic range normalization: "A - B", "A – B", "A — B", "A to B"
  // Avoid capturing signed numbers (e.g. "-10") as ranges.
  if (!/^[-−+]/.test(s)) {
    const rangeMatch = /^([^-–—\n]+?)\s*(?:[-–—]|\bto\b)\s*([^-–—\n]+)$/i.exec(s)
    if (rangeMatch) {
      const r1 = parseSingleNumber(rangeMatch[1])
      const r2 = parseSingleNumber(rangeMatch[2])
      if (r1.ok && r2.ok) {
        let v1 = r1.num.value
        let v2 = r2.num.value
        const s1 = r1.num.scaleShift
        const s2 = r2.num.scaleShift

        // Propagate scale when specified only once (e.g. "Rs. 24.99 - 34.49 Lakh")
        if (!s1 && s2) {
          v1 = shift(v1, s2)
        } else if (s1 && !s2) {
          v2 = shift(v2, s1)
        }

        let low = v1
        let high = v2
        if (cmp(low, high) > 0) [low, high] = [high, low]

        // Midpoint normalization: (low + high) / 2
        const mid = div(add(low, high), fromInt(2), Math.max(low.s, high.s) + 1) ?? low
        return {
          ok: true,
          num: {
            value: mid,
            currency: r2.num.currency ?? r1.num.currency,
            suffix: r2.num.suffix ?? r1.num.suffix,
            scaleWord: r2.num.scaleWord ?? r1.num.scaleWord,
            percent: r2.num.percent || r1.num.percent,
            approx: true,
            range: { min: low, max: high },
            isRangeMidpoint: true,
          },
        }
      }
    }
  }

  return parseSingleNumber(s)
}

/** Is this a web address? Scraped "Source" columns usually are. */
export function isUrl(raw: string): boolean {
  return /^(https?:\/\/|www\.)[^\s]+$/i.test(raw.trim())
}
