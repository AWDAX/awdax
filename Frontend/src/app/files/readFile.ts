import type { DatasetTable } from '../../api/types.ts'
import { parseDelimited, uniqueHeaders } from '../../analytics/csv.ts'

/**
 * Reads an uploaded data file in the browser into the same table shape the backend sends (every cell a
 * string), so the dashboard, questions and exports work on it unchanged. Nothing is uploaded anywhere: the
 * backend has no upload endpoint, and the file stays on this device.
 */
export type ReadResult = { ok: true; table: DatasetTable; note?: string } | { ok: false; reason: string }

export const ACCEPT = '.csv,.tsv,.txt,.json,.xlsx,text/csv,application/json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
const MAX_BYTES = 25 * 1024 * 1024

const ext = (name: string) => name.toLowerCase().split('.').pop() ?? ''

function fromMatrix(name: string, header: string[], body: string[][]): DatasetTable {
  const columns = uniqueHeaders(header)
  const rows = body.filter((r) => r.some((c) => c.trim() !== '')).map((r) => columns.map((_, i) => r[i] ?? ''))
  return { name, source_url: `file:${name}`, columns, rows, row_count: rows.length }
}

function cellText(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? '' : v.toISOString().slice(0, v.getUTCHours() || v.getUTCMinutes() ? 16 : 10)
  if (typeof v === 'object') {
    const o = v as { text?: unknown; result?: unknown; richText?: { text: string }[]; error?: string }
    if (o.richText) return o.richText.map((r) => r.text).join('')
    if (o.result !== undefined) return cellText(o.result) // formula: use its computed value
    if (o.text !== undefined) return cellText(o.text) // hyperlink
    if (o.error) return ''
  }
  return String(v)
}

async function readXlsx(file: File): Promise<ReadResult> {
  const { default: ExcelJS } = await import('exceljs')
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(await file.arrayBuffer())
  const sheet = wb.worksheets.find((ws) => ws.actualRowCount > 1) ?? wb.worksheets[0]
  if (!sheet) return { ok: false, reason: 'The workbook has no sheets.' }
  const matrix: string[][] = []
  sheet.eachRow({ includeEmpty: false }, (row) => {
    const values: string[] = []
    for (let c = 1; c <= sheet.actualColumnCount; c++) values.push(cellText(row.getCell(c).value).trim())
    matrix.push(values)
  })
  const [header = [], ...body] = matrix
  const others = wb.worksheets.length > 1 ? ` Read the sheet “${sheet.name}”; the other ${wb.worksheets.length - 1} were left out.` : ''
  return { ok: true, table: fromMatrix(file.name, header, body), note: others.trim() || undefined }
}

function readJson(file: File, text: string): ReadResult {
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return { ok: false, reason: 'This JSON file doesn’t parse.' }
  }
  const obj = data as { columns?: unknown; rows?: unknown; data?: unknown }
  if (Array.isArray(obj.columns) && Array.isArray(obj.rows)) {
    return { ok: true, table: fromMatrix(file.name, obj.columns.map(String), (obj.rows as unknown[][]).map((r) => r.map(cellText))) }
  }
  const list = Array.isArray(data) ? data : Array.isArray(obj.data) ? obj.data : null
  if (!list || list.length === 0) return { ok: false, reason: 'Expected a list of rows, e.g. [{"name": "…", "price": 1200}, …].' }
  if (Array.isArray(list[0])) {
    const [head, ...body] = list as unknown[][]
    return { ok: true, table: fromMatrix(file.name, head.map(cellText), body.map((r) => r.map(cellText))) }
  }
  const keys: string[] = []
  for (const row of list as Record<string, unknown>[]) for (const k of Object.keys(row ?? {})) if (!keys.includes(k)) keys.push(k)
  const body = (list as Record<string, unknown>[]).map((row) => keys.map((k) => cellText(row?.[k])))
  return { ok: true, table: fromMatrix(file.name, keys, body) }
}

export async function readDataFile(file: File): Promise<ReadResult> {
  if (file.size > MAX_BYTES) return { ok: false, reason: `${file.name} is over 25 MB. Split it or export fewer rows.` }
  const e = ext(file.name)
  try {
    if (e === 'xlsx') return await readXlsx(file)
    if (e === 'xls') return { ok: false, reason: 'Old .xls files can’t be read here. Save it as .xlsx or CSV in Excel first.' }
    if (['pdf', 'doc', 'docx', 'ppt', 'pptx'].includes(e)) {
      return { ok: false, reason: `Tables inside .${e} files can’t be read yet. Export the table to CSV or Excel and upload that.` }
    }
    const text = await file.text()
    if (e === 'json') return readJson(file, text)
    const t = parseDelimited(text, e === 'tsv' ? '\t' : undefined)
    if (t.columns.length < 2 && t.rows.length === 0) return { ok: false, reason: `${file.name} has no table in it.` }
    return { ok: true, table: { name: file.name, source_url: `file:${file.name}`, columns: t.columns, rows: t.rows, row_count: t.rows.length } }
  } catch (err) {
    return { ok: false, reason: `Couldn’t read ${file.name}: ${err instanceof Error ? err.message : String(err)}` }
  }
}

export const formatBytes = (n: number) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`)
