import type { Sheet, SheetColumn } from './scope.ts'

export type Dialect = 'postgres' | 'mysql' | 'sqlite' | 'sqlserver'

export const DIALECT_LABEL: Record<Dialect, string> = {
  postgres: 'PostgreSQL',
  mysql: 'MySQL',
  sqlite: 'SQLite',
  sqlserver: 'SQL Server',
}

const BATCH = 500 // SQL Server allows at most 1,000 rows per VALUES list

/** snake_case, starts with a letter, unique within the table. */
function identifiers(names: string[]): string[] {
  const seen = new Map<string, number>()
  return names.map((n) => {
    let id = n.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'column'
    if (/^\d/.test(id)) id = `c_${id}`
    const k = seen.get(id) ?? 0
    seen.set(id, k + 1)
    return k ? `${id}_${k + 1}` : id
  })
}

export const tableIdentifier = (title: string) => identifiers([title])[0].slice(0, 48)

function quoteId(d: Dialect, id: string) {
  if (d === 'mysql') return `\`${id}\``
  if (d === 'sqlserver') return `[${id}]`
  return `"${id}"`
}

function sqlType(d: Dialect, c: SheetColumn): string {
  if (c.type === 'integer') return d === 'sqlite' ? 'INTEGER' : 'BIGINT'
  if (c.type === 'decimal') {
    // Exact: DECIMAL(p, s) sized to the data, so no value is rounded on insert.
    const p = Math.max(c.precision, c.scale + 1)
    return d === 'sqlite' ? 'NUMERIC' : d === 'postgres' ? `NUMERIC(${p}, ${c.scale})` : `DECIMAL(${p}, ${c.scale})`
  }
  if (c.type === 'date') return d === 'sqlite' ? 'TEXT' : 'DATE'
  return d === 'sqlserver' ? 'NVARCHAR(MAX)' : 'TEXT'
}

function literal(d: Dialect, c: SheetColumn, v: string | null): string {
  if (v === null) return 'NULL'
  if (c.type === 'integer' || c.type === 'decimal') return v
  let s = v.replace(/'/g, "''")
  if (d === 'mysql') s = s.replace(/\\/g, '\\\\')
  return d === 'sqlserver' ? `N'${s}'` : `'${s}'`
}

/** CREATE TABLE plus batched INSERTs. Units go in column comments; values stay exact; missing is NULL. */
export function toSQL(sheet: Sheet, dialect: Dialect, table: string, meta: { title: string; source?: string; filters?: string }): string {
  // The unit joins the column name ("price" → price_inr) unless the scraped name already says it (price_inr).
  const withUnit = (name: string, unit?: string) => {
    if (!unit) return name
    const word = unit === '%' ? 'pct' : unit
    return new RegExp(`(^|[^a-z])${word.replace(/[^a-z0-9]/gi, '')}$`, 'i').test(name) ? name : `${name} ${word}`
  }
  const ids = identifiers(sheet.columns.map((c) => withUnit(c.name, c.unit)))
  const t = quoteId(dialect, table)
  // Titles and URLs come from users and scraped pages: one line each, so nothing escapes the comment.
  const oneLine = (s: string) => s.replace(/[\r\n]+/g, ' ')
  const lines: string[] = [
    `-- Exported from AWDAX on ${new Date().toISOString()}`,
    `-- ${oneLine(meta.title)}${meta.source ? ` · source: ${oneLine(meta.source)}` : ''}`,
    `-- ${sheet.rows.length} rows${meta.filters ? ` · filters: ${oneLine(meta.filters)}` : ''}. Missing values are NULL, never 0.`,
    ...sheet.columns.flatMap((c, i) => (c.unit ? [`-- ${ids[i]}: in ${oneLine(c.unit)}`] : [])),
    '',
    `CREATE TABLE ${t} (`,
    sheet.columns.map((c, i) => `  ${quoteId(dialect, ids[i])} ${sqlType(dialect, c)}`).join(',\n'),
    ');',
    '',
  ]
  const cols = ids.map((id) => quoteId(dialect, id)).join(', ')
  for (let i = 0; i < sheet.rows.length; i += BATCH) {
    const values = sheet.rows
      .slice(i, i + BATCH)
      .map((r) => `  (${r.map((v, j) => literal(dialect, sheet.columns[j], v)).join(', ')})`)
      .join(',\n')
    lines.push(`INSERT INTO ${t} (${cols}) VALUES\n${values};`, '')
  }
  return lines.join('\n')
}
