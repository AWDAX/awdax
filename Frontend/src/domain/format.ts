import type { CellValue, Column } from './types.ts'

const SYMBOL: Record<string, string> = { INR: '₹', USD: '$' }

/** ₹25,000 · $1,800,000, or compact: ₹25k · $1.8M */
export function formatMoney(n: number, currency = 'INR', compact = false): string {
  const sym = SYMBOL[currency] ?? `${currency} `
  if (!compact) return `${sym}${n.toLocaleString(currency === 'INR' ? 'en-IN' : 'en-US')}`
  if (n >= 1_000_000) return `${sym}${trim(n / 1_000_000)}M`
  if (n >= 1_000) return `${sym}${trim(n / 1_000)}k`
  return `${sym}${n}`
}

const trim = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, ''))

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Dates are 'YYYY-MM-DD' or full ISO strings, read as UTC. 'short' = 14 Jan, 'long' = 14 Jan 2026. */
export function formatDate(iso: string, style: 'short' | 'long' = 'short'): string {
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso)
  const base = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`
  return style === 'long' ? `${base} ${d.getUTCFullYear()}` : base
}

export const monthLabel = (monthIndex: number) => MONTHS[monthIndex]

/** 25 Sep 2026, 04:31 UTC */
export function formatCaptured(iso: string): string {
  const d = new Date(iso)
  const hh = String(d.getUTCHours()).padStart(2, '0')
  const mm = String(d.getUTCMinutes()).padStart(2, '0')
  return `${formatDate(iso, 'long')}, ${hh}:${mm} UTC`
}

export function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** How a cell value reads in a table. Missing values are said plainly, never blank. */
export function formatValue(value: CellValue | null, column: Column, compact = false): string {
  if (value === null) return 'Not found'
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  switch (column.type) {
    case 'money':
      return formatMoney(Number(value), column.currency, compact)
    case 'date':
      return formatDate(String(value), compact ? 'short' : 'long')
    case 'url':
      return domainOf(String(value))
    case 'number':
      return Number.isInteger(value) ? Number(value).toLocaleString('en-IN') : Number(value).toFixed(1)
    default:
      return String(value)
  }
}
