import type { Sheet, SheetValue } from './scope.ts'

/**
 * Text writers. Values arrive already exact (decimal strings, ISO dates, null), so nothing here rounds.
 * `raw: true` writes the cells exactly as scraped instead.
 */
export interface TextOptions {
  raw?: boolean
}

const header = (s: Sheet) => s.columns.map((c) => (c.unit ? `${c.name} (${c.unit})` : c.name))
const body = (s: Sheet, o: TextOptions): SheetValue[][] => (o.raw ? s.raw.map((r) => r.map((v) => (v === '' ? null : v))) : s.rows)
const isNumber = (s: Sheet, i: number, o: TextOptions) => !o.raw && (s.columns[i]?.type === 'integer' || s.columns[i]?.type === 'decimal')

/**
 * Scraped text is untrusted: a cell like "=HYPERLINK(…)" would run as a formula when the file is opened.
 * Text cells starting with = + - @ get a leading apostrophe (OWASP CSV injection advice). Number cells
 * are left exact; a negative number is a number, not a formula.
 */
export const defuse = (v: string) => (/^[=+\-@\t\r]/.test(v) ? `'${v}` : v)

function delimited(s: Sheet, o: TextOptions, sep: string): string {
  const cell = (v: SheetValue, i: number) => {
    if (v === null) return ''
    const safe = isNumber(s, i, o) ? v : defuse(v)
    if (sep === '\t') return safe.replace(/[\t\r\n]+/g, ' ')
    return /[",\r\n]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe
  }
  return [header(s).map((h) => cell(h, -1)), ...body(s, o).map((r) => r.map(cell))].map((r) => r.join(sep)).join('\r\n')
}

/** CSV with a UTF-8 byte-order mark, so Excel and Power BI read ₹ correctly. */
export const toCSV = (s: Sheet, o: TextOptions = {}) => `\ufeff${delimited(s, o, ',')}`
export const toTSV = (s: Sheet, o: TextOptions = {}) => delimited(s, o, '\t')

function objects(s: Sheet, o: TextOptions) {
  const keys = header(s)
  // JSON numbers are exact only up to ~15 digits; longer ones stay strings so no digit is lost.
  return body(s, o).map((r) =>
    Object.fromEntries(r.map((v, i) => [keys[i], v !== null && isNumber(s, i, o) && v.replace(/[-.]/g, '').length <= 15 ? Number(v) : v])),
  )
}

export const toJSON = (s: Sheet, o: TextOptions = {}) => JSON.stringify(objects(s, o), null, 2)
export const toJSONL = (s: Sheet, o: TextOptions = {}) => objects(s, o).map((x) => JSON.stringify(x)).join('\n')

const xmlEscape = (v: string) => v.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const xmlName = (n: string) => n.replace(/[^A-Za-z0-9_.-]+/g, '_').replace(/^([^A-Za-z_])/, '_$1') || 'field'

export function toXML(s: Sheet, o: TextOptions = {}): string {
  const names = s.columns.map((c) => xmlName(c.name))
  const rows = body(s, o).map((r) => {
    const cells = r.map((v, i) => (v === null ? `    <${names[i]} xsi:nil="true"/>` : `    <${names[i]}>${xmlEscape(v)}</${names[i]}>`))
    return `  <row>\n${cells.join('\n')}\n  </row>`
  })
  return `<?xml version="1.0" encoding="UTF-8"?>\n<rows xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n${rows.join('\n')}\n</rows>\n`
}

export function toMarkdown(s: Sheet, o: TextOptions = {}): string {
  const esc = (v: SheetValue) => (v === null ? '' : v.replace(/\|/g, '\\|').replace(/\r?\n/g, ' '))
  const align = s.columns.map((_, i) => (isNumber(s, i, o) ? '---:' : '---'))
  return [header(s), align, ...body(s, o)].map((r) => `| ${r.map((v) => esc(v as SheetValue)).join(' | ')} |`).join('\n')
}
