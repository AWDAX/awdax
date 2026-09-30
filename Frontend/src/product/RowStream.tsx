import type { ReactNode } from 'react'
import { formatValue } from '../domain/format.ts'
import type { Cell, Column, Row, Source } from '../domain/types.ts'
import { SourceChip } from './SourceChip.tsx'

type Props = {
  /** Three columns: the first names the row, the second hides in narrow containers. */
  columns: [Column, Column, Column]
  rows: Row[]
  /** How many rows have arrived. */
  shown: number
  sources: Source[]
  /** Rows the window holds before older ones scroll up. */
  windowRows?: number
  footer?: ReactNode
}

const ROW_PX = 40

// The source column is widest after the name: a truncated domain is a receipt you can't read.
const grid =
  'grid grid-cols-[minmax(0,1.1fr)_minmax(0,0.75fr)_minmax(0,1.45fr)] gap-x-3 ' +
  '@lg:grid-cols-[minmax(0,1.25fr)_minmax(0,0.85fr)_minmax(0,0.7fr)_minmax(0,1.45fr)]'

const label = 'font-sans text-small font-semibold text-ink'

/** Rows as they arrive during a run, each with the source it came from. */
export function RowStream({ columns, rows, shown, sources, windowRows = 7, footer }: Props) {
  const [first, second, third] = columns
  const offset = Math.max(0, shown - windowRows) * ROW_PX
  const byId = new Map(sources.map((s) => [s.id, s]))

  return (
    <section aria-label="Rows" className="@container flex flex-col">
      <header className="flex min-h-10 items-center justify-between gap-3">
        <h3 className={label}>Rows</h3>
        <p className="text-small text-ink-2" aria-live="off">
          <span className="font-medium text-ink tabular-nums">{shown}</span> found
        </p>
      </header>

      <div role="table" aria-label="Rows found so far" aria-rowcount={shown + 1}>
        <div role="rowgroup">
          <div role="row" className={`${grid} h-8 items-center border-b border-line text-micro text-ink-3`}>
            <span role="columnheader" className="truncate">{first.label}</span>
            <span role="columnheader" className="hidden truncate @lg:block">{second.label}</span>
            <span role="columnheader" className="truncate">{third.label}</span>
            <span role="columnheader" className="truncate">Source</span>
          </div>
        </div>

        <div role="rowgroup" className="relative overflow-hidden" style={{ height: windowRows * ROW_PX }}>
          {shown === 0 && (
            <p className="absolute inset-0 grid place-items-center text-small text-ink-3">Rows appear here as sources return them.</p>
          )}
          <div
            role="presentation"
            className="transition-transform duration-700 ease-soft"
            style={{ transform: `translateY(-${offset}px)` }}
          >
            {rows.slice(0, shown).map((row) => {
              const src = byId.get(row.sourceIds[0])
              return (
                <div
                  role="row"
                  key={row.id}
                  className={`${grid} h-10 animate-row-in items-center border-b border-line text-small`}
                >
                  <Value rowId={row.id} cell={row.cells[first.key]} column={first} strong />
                  <Value rowId={row.id} cell={row.cells[second.key]} column={second} className="hidden @lg:block" />
                  <Value rowId={row.id} cell={row.cells[third.key]} column={third} />
                  <span role="cell" className="min-w-0">
                    {src && (
                      <SourceChip domain={src.domain} method={src.method} more={row.sourceIds.length - 1} shortWhenNarrow />
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {footer}
    </section>
  )
}

type ValueProps = { rowId: string; cell?: Cell; column: Column; strong?: boolean; className?: string }

// data-to="{rowId}:{column}" is where the hero's TraceLayer ends a line drawn from the source page.
function Value({ rowId, cell, column, strong = false, className = '' }: ValueProps) {
  const to = `${rowId}:${column.key}`
  if (!cell || cell.status === 'not_found') {
    return (
      <span role="cell" data-to={to} className={`truncate text-ink-3 ${className}`}>
        Not found
      </span>
    )
  }
  return (
    <span role="cell" data-to={to} className={`truncate tabular-nums ${strong ? 'font-medium text-ink' : 'text-ink-2'} ${className}`}>
      {formatValue(cell.value, column, true)}
      {cell.status === 'conflict' && (
        <span className="ml-1 text-ink-3" title="Sources disagree on this value">
          <span aria-hidden>≠</span>
          <span className="sr-only">(sources disagree)</span>
        </span>
      )}
    </span>
  )
}
