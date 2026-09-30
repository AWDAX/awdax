import type { DatasetTable, StreamedRows } from './types.ts'

/** True when every visible row has a score record, so a live frame can be appended without duplicating. */
export function canMerge(current: DatasetTable | null): boolean {
  if (!current || current.rows.length === 0) return true
  return (current.records?.length ?? 0) === current.rows.length
}

/**
 * Append accepted rows from a live `rows` frame. Rows already stored (same id) are skipped.
 * New columns are added at the end; older rows gain an empty cell there.
 */
export function mergeStreamedRows(current: DatasetTable | null, message: StreamedRows): DatasetTable {
  const base = current ?? { columns: [], rows: [], records: [] }
  const columns = [...base.columns]
  for (const name of message.columns) if (!columns.includes(name)) columns.push(name)
  const at = new Map(message.columns.map((name, index) => [name, index]))
  const seen = new Set((base.records ?? []).map((record) => record.id))
  const rows = base.rows.map((row) => {
    const next = row.slice()
    while (next.length < columns.length) next.push('')
    return next
  })
  const records = [...(base.records ?? [])]
  message.records.forEach((record, index) => {
    if (!record.id || seen.has(record.id)) return
    seen.add(record.id)
    const source = message.rows[index] ?? []
    rows.push(columns.map((name) => {
      const column = at.get(name)
      return column === undefined ? '' : (source[column] ?? '')
    }))
    records.push(record)
  })
  return { columns, rows, records, row_count: message.accepted_total }
}
