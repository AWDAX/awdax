/** A column of an answer's result: its name and what kind of value it holds. */
export type ResultColumn = { name: string; type: string }
type Cell = string | number | null

const SHOWN = 50

const cellText = (v: Cell) => (v === null || v === '' ? '—' : typeof v === 'number' ? v.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : v)

/**
 * An answer's result as a table whose header is its schema: each column's name, and under it the kind of value
 * (number, money, text, …). Shows the first 50 rows.
 */
export function ResultTable({ columns, rows, caption }: { columns: ResultColumn[]; rows: Cell[][]; caption: string }) {
  const numeric = columns.map((c) => ['number', 'money', 'percent'].includes(c.type))
  return (
    <div className="overflow-x-auto rounded-control border-2 border-line">
      <table className="w-full text-small">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-sunken">
          <tr>
            {columns.map((c, i) => (
              <th key={i} scope="col" className={`px-3 py-2 align-bottom font-semibold ${numeric[i] ? 'text-right' : 'text-left'}`}>
                {c.name}
                <span className="block font-mono text-micro font-normal text-ink-3">{c.type}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, SHOWN).map((r, ri) => (
            <tr key={ri} className="border-t border-line">
              {columns.map((_, ci) => (
                <td key={ci} className={`px-3 py-1.5 ${numeric[ci] ? 'text-right font-mono tabular-nums' : ''}`}>
                  {cellText(r[ci] ?? null)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > SHOWN && <p className="border-t border-line px-3 py-1.5 text-micro text-ink-3">First {SHOWN} of {rows.length} rows.</p>}
    </div>
  )
}
