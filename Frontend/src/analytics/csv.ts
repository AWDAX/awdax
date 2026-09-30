/**
 * RFC 4180 delimited text → header + rows, all strings. Handles quoted fields with commas, quotes ("") and
 * line breaks, a UTF-8 byte-order mark, CRLF, and picks the delimiter (comma, semicolon, tab or pipe) from
 * the first line. Values are kept exactly as written; the profile parses them later.
 */
export interface Delimited {
  columns: string[]
  rows: string[][]
  delimiter: string
}

const CANDIDATES = [',', ';', '\t', '|']

function detect(text: string): string {
  const firstLine = text.slice(0, text.search(/\r?\n|$/))
  let best = ','
  let bestCount = 0
  for (const d of CANDIDATES) {
    let count = 0
    let quoted = false
    for (const ch of firstLine) {
      if (ch === '"') quoted = !quoted
      else if (ch === d && !quoted) count++
    }
    if (count > bestCount) [best, bestCount] = [d, count]
  }
  return best
}

/** Unique, non-empty headers: blanks become "Column 3", repeats become "Price (2)". */
export function uniqueHeaders(raw: string[]): string[] {
  const seen = new Map<string, number>()
  return raw.map((h, i) => {
    const base = h.trim() || `Column ${i + 1}`
    const n = seen.get(base.toLowerCase()) ?? 0
    seen.set(base.toLowerCase(), n + 1)
    return n ? `${base} (${n + 1})` : base
  })
}

export function parseDelimited(input: string, delimiter?: string): Delimited {
  const text = input.charCodeAt(0) === 0xfeff ? input.slice(1) : input
  const d = delimiter ?? detect(text)
  const records: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"'
          i++
        } else quoted = false
      } else field += ch
      continue
    }
    if (ch === '"' && field === '') quoted = true
    else if (ch === d) {
      row.push(field)
      field = ''
    } else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++
      row.push(field)
      records.push(row)
      row = []
      field = ''
    } else field += ch
  }
  if (field !== '' || row.length > 0) {
    row.push(field)
    records.push(row)
  }
  const nonEmpty = records.filter((r) => r.some((c) => c.trim() !== ''))
  const [head = [], ...body] = nonEmpty
  const width = Math.max(head.length, ...body.map((r) => r.length))
  const columns = uniqueHeaders(Array.from({ length: width }, (_, i) => head[i] ?? ''))
  const rows = body.map((r) => Array.from({ length: width }, (_, i) => r[i] ?? ''))
  return { columns, rows, delimiter: d }
}
