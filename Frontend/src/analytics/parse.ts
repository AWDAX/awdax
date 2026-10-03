import { add, cmp, fromInt, fromString, mul, neg, shift } from './decimal.ts'
import type { Dec } from './decimal.ts'

/**
 * Scraped cells are strings ("₹12.5 lakh", "1,44,879", "(1,200)", "18.4%", "450 km"). This reads them into
 * exact decimals and says what it read, so the UI can show the unit and why a cell was left out.
 * A missing value ("N/A", "—") is never read as 0. A range of one measured quantity counts as its lowest value.
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
  /** The cell was a range ("₹11.45 – ₹26.95 Lakh"): `value` is its low end. */
  range?: { low: Dec; high: Dec }
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

/** One number: approx mark, brackets, currency, sign, percent, digits, scale word, unit. */
function readOne(text: string): NumberRead {
  let s = text
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
 * "₹11.45 – ₹26.95 Lakh", "450 - 500 km", "10 to 15 Lakh": both ends of one quantity, read as the lower end.
 * Null unless that is clear, so everything else keeps the single-number rules and their refusal.
 */
function readRange(s: string): NumberRead | null {
  if (/^[-−+(]/.test(s)) return null
  const m = /^(.+?)\s*(?:[-–—]|\bto\b)\s*(.+)$/i.exec(s)
  // Another "to" or an "and" is "Up to 500", "500 and above" or a chain, not two ends: those stay refused.
  if (!m || /\b(to|and)\b/i.test(`${m[1]} ${m[2]}`)) return null
  const a = readOne(m[1])
  const b = readOne(m[2])
  if (!a.ok || !b.ok) return null
  const x = a.num
  const y = b.num

  const unit = (n: ParsedNumber) => n.currency || n.scaleWord || n.suffix || n.percent
  // Bare digits ("2024-25", "98765-43210") are years, pages and phone numbers as often as quantities.
  if (!unit(x) && !unit(y)) return null
  if (x.currency && y.currency && x.currency !== y.currency) return null
  if (x.suffix && y.suffix && x.suffix !== y.suffix) return null
  if ((x.percent || y.percent) && (x.currency || y.currency || x.suffix || y.suffix)) return null
  // "km/h in 9.5 s" gets through readOne as a unit; with a digit in it, it is a phrase.
  if ([x.suffix, y.suffix].some((u) => u && /\d/.test(u))) return null

  let low = x.value
  let high = y.value
  // A scale word written once covers both ends ("24.99 - 34.49 Lakh"); two words are each read as written.
  const power = (word: string) => SCALES.find(([, , name]) => name === word)?.[1] ?? 0
  if (x.scaleWord && !y.scaleWord) high = shift(high, power(x.scaleWord))
  else if (y.scaleWord && !x.scaleWord) low = shift(low, power(y.scaleWord))
  if (cmp(low, high) > 0) return null
  return { ok: true, num: { ...y, ...x, value: low, range: { low, high } } }
}

/** Reads one cell as a number. */
export function parseNumber(input: string | number | null | undefined): NumberRead {
  if (input === null || input === undefined) return { ok: false, missing: true, reason: 'empty' }
  if (typeof input === 'number') {
    if (!Number.isFinite(input)) return { ok: false, missing: false, reason: 'not a finite number' }
    const d = fromString(String(input))
    return d ? { ok: true, num: { value: d } } : { ok: false, missing: false, reason: 'not a number' }
  }
  // A footnote mark at the very end ("₹7.99 Lakh*") is not part of the number; anywhere else it still stops the read.
  const s = input.trim().replace(/\s*[*†‡]+$/, '')
  if (isMissingText(s)) return { ok: false, missing: true, reason: 'marked as missing' }
  const range = readRange(s)
  if (range) return range
  if (/\b(to|and)\b|\d\s*[-–—]\s*\d/i.test(s)) return { ok: false, missing: false, reason: 'a range, not one number' }
  return readOne(s)
}

/** Is this a web address? Scraped "Source" columns usually are. */
export function isUrl(raw: string): boolean {
  return /^(https?:\/\/|www\.)[^\s]+$/i.test(raw.trim())
}
