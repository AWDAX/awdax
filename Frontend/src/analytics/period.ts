/**
 * Reads scraped dates and periods ("Jan 2024", "2024-01", "Q1 FY25", "14/01/2026", "January") into keys
 * that sort in time order. Slashed dates are read day/month/year (Indian usage) unless the numbers
 * only fit month/day; `ambiguous` says so, and the profile reports it.
 */

export type Grain = 'year' | 'fiscal' | 'quarter' | 'month' | 'day' | 'monthName'

export interface Period {
  /** Sorts in time order within one grain: '2024', 'FY2024-25', '2024-Q1', '2024-01', '2024-01-14', 'M01'. */
  key: string
  grain: Grain
  label: string
  /** For month and day grains: the year, so a Month + Year pair can be checked. */
  year?: number
  ambiguous?: boolean
}

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_RE = /^(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?$/i

export function monthIndex(word: string): number {
  const m = MONTH_RE.exec(word.trim())
  return m ? MONTHS.findIndex((x) => x.toLowerCase() === m[1].slice(0, 3).toLowerCase()) : -1
}

const pad = (n: number) => String(n).padStart(2, '0')
const fullYear = (y: string) => (y.length === 2 ? 2000 + Number(y) : Number(y))
const plausibleYear = (y: number) => y >= 1900 && y <= 2100

function month(y: number, m: number): Period | null {
  if (!plausibleYear(y) || m < 0 || m > 11) return null
  return { key: `${y}-${pad(m + 1)}`, grain: 'month', label: `${MONTHS[m]} ${y}`, year: y }
}

function day(y: number, m: number, d: number, ambiguous = false): Period | null {
  if (!plausibleYear(y) || m < 0 || m > 11 || d < 1) return null
  const probe = new Date(Date.UTC(y, m, d))
  if (probe.getUTCMonth() !== m) return null
  return { key: `${y}-${pad(m + 1)}-${pad(d)}`, grain: 'day', label: `${d} ${MONTHS[m]} ${y}`, year: y, ambiguous }
}

export function parsePeriod(input: string | number | null | undefined): Period | null {
  if (input === null || input === undefined) return null
  const s = String(input).trim().replace(/\s+/g, ' ')
  if (!s) return null
  let m: RegExpExecArray | null

  // 2024
  if ((m = /^(\d{4})$/.exec(s))) {
    const y = Number(m[1])
    return plausibleYear(y) ? { key: m[1], grain: 'year', label: m[1], year: y } : null
  }
  // FY 2024-25, FY24-25, FY2025, FY25
  if ((m = /^fy\s?'?(\d{2}|\d{4})(?:\s?[-/–]\s?(\d{2}|\d{4}))?$/i.exec(s))) {
    const end = m[2] ? fullYear(m[2]) : fullYear(m[1])
    const start = m[2] ? fullYear(m[1]) : end - 1
    if (!plausibleYear(start) || end !== start + 1) return null
    return { key: `FY${start}-${String(end).slice(2)}`, grain: 'fiscal', label: `FY ${start}–${String(end).slice(2)}`, year: start }
  }
  // Q1 2024, 2024 Q1, Q1-24, Q1 FY25 (fiscal quarters are keyed by their fiscal year)
  if ((m = /^q([1-4])\s?[-/ ]?\s?(?:fy\s?)?'?(\d{2}|\d{4})$/i.exec(s) ?? /^(\d{4})\s?[-/ ]?\s?q([1-4])$/i.exec(s))) {
    const [q, y] = /^q/i.test(s) ? [m[1], fullYear(m[2])] : [m[2], fullYear(m[1])]
    if (!plausibleYear(y)) return null
    return { key: `${y}-Q${q}`, grain: 'quarter', label: `Q${q} ${y}`, year: y }
  }
  // 2024-01-14 or 2024/01/14, optionally with a time
  if ((m = /^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[T ][\d:.]+(?:z|[+-]\d{2}:?\d{2})?)?$/i.exec(s))) {
    return day(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  }
  // 2024-01, 2024/01
  if ((m = /^(\d{4})[-/.](\d{1,2})$/.exec(s))) return month(Number(m[1]), Number(m[2]) - 1)
  // 01/2024, 1-2024
  if ((m = /^(\d{1,2})[-/.](\d{4})$/.exec(s))) return month(Number(m[2]), Number(m[1]) - 1)
  // 14/01/2026 (day first), 01/14/2026 (month first only when the day can't be the first number)
  if ((m = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})$/.exec(s))) {
    const a = Number(m[1])
    const b = Number(m[2])
    const y = fullYear(m[3])
    if (b > 12 && a <= 12) return day(y, a - 1, b)
    return day(y, b - 1, a, a <= 12 && b <= 12 && a !== b)
  }
  // Jan 2024, January 2024, Jan-24, Jan'24, 2024 Jan
  if ((m = /^([a-z]+\.?)[\s\-'’/,]+'?(\d{2}|\d{4})$/i.exec(s))) {
    const mi = monthIndex(m[1])
    if (mi >= 0) return month(fullYear(m[2]), mi)
  }
  if ((m = /^(\d{4})[\s\-/,]+([a-z]+\.?)$/i.exec(s))) {
    const mi = monthIndex(m[2])
    if (mi >= 0) return month(Number(m[1]), mi)
  }
  // 14 Jan 2026, 14-Jan-2026, Jan 14, 2026
  if ((m = /^(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+([a-z]+\.?)[\s\-/,]+(\d{2}|\d{4})$/i.exec(s))) {
    const mi = monthIndex(m[2])
    if (mi >= 0) return day(fullYear(m[3]), mi, Number(m[1]))
  }
  if ((m = /^([a-z]+\.?)\s(\d{1,2})(?:st|nd|rd|th)?,?\s(\d{4})$/i.exec(s))) {
    const mi = monthIndex(m[1])
    if (mi >= 0) return day(Number(m[3]), mi, Number(m[2]))
  }
  // January (no year): sorts by month
  const mi = monthIndex(s)
  if (mi >= 0) return { key: `M${pad(mi + 1)}`, grain: 'monthName', label: MONTHS[mi] }
  return null
}

export type Bucket = 'year' | 'quarter' | 'month'

/**
 * A coarser period for grouping: 2024-03-14 → 2024-03 (month), 2024-Q1 (quarter) or 2024 (year).
 * Periods that can't be made coarser this way (fiscal years, month names) come back unchanged.
 */
export function bucketOf(p: Period, bucket: Bucket): Period {
  const m = /^(\d{4})-(\d{2})/.exec(p.key)
  const y = p.year ?? (m ? Number(m[1]) : undefined)
  if (y === undefined || p.grain === 'fiscal' || p.grain === 'monthName' || p.grain === 'year') return p
  if (bucket === 'year') return { key: String(y), grain: 'year', label: String(y), year: y }
  if (bucket === 'quarter') {
    const q = p.grain === 'quarter' ? Number(p.key.slice(-1)) : m ? Math.floor((Number(m[2]) - 1) / 3) + 1 : 1
    return { key: `${y}-Q${q}`, grain: 'quarter', label: `Q${q} ${y}`, year: y }
  }
  if (!m || p.grain === 'quarter') return p
  const mi = Number(m[2]) - 1
  return { key: `${y}-${m[2]}`, grain: 'month', label: `${MONTHS[mi]} ${y}`, year: y }
}

/**
 * A period's position on a continuous timeline, in its own grain's steps (months, quarters, days…).
 * Charts place points by this, so missing months show as gaps instead of being squeezed out.
 */
export function ordinal(key: string): number | null {
  let m: RegExpExecArray | null
  if ((m = /^(\d{4})$/.exec(key))) return Number(m[1])
  if ((m = /^FY(\d{4})-\d{2}$/.exec(key))) return Number(m[1])
  if ((m = /^(\d{4})-Q([1-4])$/.exec(key))) return Number(m[1]) * 4 + Number(m[2]) - 1
  if ((m = /^(\d{4})-(\d{2})$/.exec(key))) return Number(m[1]) * 12 + Number(m[2]) - 1
  if ((m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key))) return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / 86_400_000
  if ((m = /^M(\d{2})$/.exec(key))) return Number(m[1]) - 1
  return null
}

/** A Month column plus a Year column read together, e.g. "February" + "2024" → Feb 2024. */
export function combineMonthYear(monthCell: Period | null, yearCell: Period | null): Period | null {
  if (!monthCell || !yearCell || monthCell.grain !== 'monthName' || yearCell.grain !== 'year') return null
  return month(Number(yearCell.key), Number(monthCell.key.slice(1)) - 1)
}
