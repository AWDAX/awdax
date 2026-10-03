import { useCallback, useRef, useState } from 'react'
import { AGG_LABEL } from '../../analytics/aggregate.ts'
import type { QueryResult } from '../../analytics/aggregate.ts'
import { plural } from '../../analytics/format.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { Popover } from '../../ui/Popover.tsx'

/** "Row 12 · Jun 2024 · 4W": a row named by its first two category or date values, so it can be found. */
function rowName(p: TableProfile, row: number): string {
  const keys = p.columns.filter((c) => !c.virtual && (c.kind === 'category' || c.kind === 'period' || c.kind === 'text')).slice(0, 2)
  const parts = keys.map((c) => c.labels[row]).filter(Boolean)
  return `Row ${row + 1}${parts.length ? ` · ${parts.join(' · ')}` : ''}`
}

/**
 * The line under every tile saying exactly what was counted: the aggregate, rows used, and which rows were
 * blank or left out and why. "Missing beats invented": a cell that wasn't a number is listed, never read as 0.
 */
export function PrecisionNote({ profile, result }: { profile: TableProfile; result: QueryResult }) {
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLButtonElement>(null)
  const close = useCallback(() => setOpen(false), [])
  const q = result.query
  const measure = q.measure !== undefined ? profile.columns[q.measure] : undefined
  const how = q.agg === 'count' || !measure ? 'Count of rows' : `${AGG_LABEL[q.agg]} of ${measure.label}`
  const avgNote = q.agg === 'avg' ? `, rounded half-to-even to ${result.scale} decimals` : ''
  const rangeNote = result.ranged > 0 ? ` · ${plural(result.ranged, 'range')} counted at the lowest value` : ''
  const text = `${how}${avgNote} · ${plural(result.used, 'row')} used${rangeNote}`
  const missing = result.blank.length + result.excluded.length

  return (
    <div className="text-micro text-ink-3">
      <p className="flex items-baseline gap-1.5">
        <span className="min-w-0 flex-1 truncate" title={text}>
          {text}
        </span>
        {missing > 0 && (
          <button
            ref={anchor}
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="shrink-0 underline decoration-blocked decoration-2 underline-offset-2 hover:text-ink"
          >
            {[result.blank.length ? `${result.blank.length} blank` : '', result.excluded.length ? `${result.excluded.length} left out` : ''].filter(Boolean).join(' · ')}
          </button>
        )}
      </p>
      <Popover anchor={anchor} open={open} onClose={close} align="start" label="Rows not counted" className="w-80 max-w-[calc(100vw-16px)] p-3">
        <p className="mb-2 text-small font-semibold text-ink">Not counted in this chart</p>
        <ul className="flex max-h-60 flex-col gap-1.5 overflow-y-auto font-mono text-micro text-ink-2">
          {result.excluded.map((e) => (
            <li key={`x${e.row}`}>
              <span className="text-ink">{rowName(profile, e.row)}</span>: “{e.raw}” in {e.column}, {e.reason}
            </li>
          ))}
          {result.blank.map((b) => (
            <li key={`b${b.row}-${b.column}`}>
              <span className="text-ink">{rowName(profile, b.row)}</span>: no {b.column.toLowerCase()} in the source
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  )
}
