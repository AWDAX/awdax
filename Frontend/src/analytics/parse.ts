import { add, fromInt, fromString, mul, neg, shift } from './decimal.ts'
import type { Dec } from './decimal.ts'

/**
 * Scraped cells are strings ("₹12.5 lakh", "1,44,879", "(1,200)", "18.4%", "450 km"). This reads them into
 * exact decimals and says what it read, so the UI can show the unit and why a cell was left out.
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
  /** Marked "~", "approx." or "about" in the source. */
  approx?: boolean
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

/** Reads one cell as a number. */
export function parseNumber(input: string | number | null | undefined): NumberRead {
  if (input === null || input === undefined) return { ok: false, missing: true, reason: 'empty' }
  if (typeof input === 'number') {
    if (!Number.isFinite(input)) return { ok: false, missing: false, reason: 'not a finite number' }
    const d = fromString(String(input))
    return d ? { ok: true, num: { value: d } } : { ok: false, missing: false, reason: 'not a number' }
  }
  let s = input.trim()
  if (isMissingText(s)) return { ok: false, missing: true, reason: 'marked as missing' }
  const num: Partial<ParsedNumber> = {}

  if (/^(~|≈|approx\.?|about|around|circa|ca\.)\s*/i.test(s)) {
    num.approx = true
    s = s.replace(/^(~|≈|approx\.?|about|around|circa|ca\.)\s*/i, '')
  }
  if (/\b(to|and)\b|\d\s*[-–—]\s*\d/i.test(s)) return { ok: false, missing: false, reason: 'a range, not one number' }

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

/** Is this a web address? Scraped "Source" columns usually are. */
export function isUrl(raw: string): boolean {
  return /^(https?:\/\/|www\.)[^\s]+$/i.test(raw.trim())
}
