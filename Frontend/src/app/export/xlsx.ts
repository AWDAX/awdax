import type { Sheet } from './scope.ts'

/**
 * Excel .xlsx via exceljs, loaded only when someone exports (it's large). Number cells are real numbers with
 * a format matching their decimals; dates are real dates; missing cells stay empty. A second sheet says
 * where the data came from and what was filtered.
 */
export async function toXLSX(sheet: Sheet, meta: { title: string; source?: string; filters?: string; raw?: boolean }): Promise<Blob> {
  const { default: ExcelJS } = await import('exceljs')
  const wb = new ExcelJS.Workbook()
  wb.creator = 'AWDAX'
  wb.created = new Date()

  const ws = wb.addWorksheet('Data', { views: [{ state: 'frozen', ySplit: 1 }] })
  ws.columns = sheet.columns.map((c) => ({
    header: c.unit ? `${c.name} (${c.unit})` : c.name,
    key: c.name,
    width: Math.min(48, Math.max(10, c.name.length + 4)),
  }))
  ws.getRow(1).font = { bold: true }

  const rows = meta.raw ? sheet.raw : sheet.rows
  rows.forEach((r) => {
    ws.addRow(
      r.map((v, i) => {
        if (v === null || v === '') return null
        const c = sheet.columns[i]
        if (meta.raw) return v
        // Excel stores doubles: exact up to 15 significant digits. Longer values stay text so no digit is lost.
        if ((c.type === 'integer' || c.type === 'decimal') && v.replace(/[-.]/g, '').length <= 15) return Number(v)
        if (c.type === 'date' && /^\d{4}-\d{2}-\d{2}$/.test(v)) return new Date(`${v}T00:00:00Z`)
        return v
      }),
    )
  })
  if (!meta.raw) {
    sheet.columns.forEach((c, i) => {
      const col = ws.getColumn(i + 1)
      if (c.type === 'decimal') col.numFmt = c.scale ? `#,##0.${'0'.repeat(c.scale)}` : '#,##0'
      if (c.type === 'integer') col.numFmt = '#,##0'
      if (c.type === 'date') col.numFmt = 'yyyy-mm-dd'
    })
  }
  ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: Math.max(1, sheet.columns.length) } }

  const about = wb.addWorksheet('About')
  about.columns = [{ width: 18 }, { width: 80 }]
  about.addRows([
    ['Title', meta.title],
    ['Source', meta.source ?? ''],
    ['Exported', new Date().toISOString()],
    ['Rows', sheet.rows.length],
    ['Filters', meta.filters || 'None'],
    ['Values', meta.raw ? 'Exactly as scraped (text)' : 'Parsed: exact numbers, dates as dates, units in the headers'],
    ['Missing', 'Empty cells were not found in the source. They are never filled with 0.'],
  ])
  about.getColumn(1).font = { bold: true }

  const buf = await wb.xlsx.writeBuffer()
  return new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
}
