import { useMemo, useState } from 'react'
import { filterRows } from '../../analytics/aggregate.ts'
import type { Filter } from '../../analytics/aggregate.ts'
import { cmp } from '../../analytics/decimal.ts'
import { formatFor } from '../../analytics/format.ts'
import { isMissingText } from '../../analytics/parse.ts'
import { isNumeric } from '../../analytics/profile.ts'
import type { ColumnProfile, TableProfile } from '../../analytics/profile.ts'
import { domainOf } from '../../domain/format.ts'
import { ChevronIcon } from '../../ui/appIcons.tsx'

const PAGE = 50

type Sort = { col: number; dir: 1 | -1 } | null

function compareRows(col: ColumnProfile, a: number, b: number): number {
  if (col.numbers) {
    const x = col.numbers[a]
    const y = col.numbers[b]
    if (x && y) return cmp(x, y)
    return x ? -1 : y ? 1 : 0
  }
  if (col.periods) return (col.periods[a]?.key ?? '￿').localeCompare(col.periods[b]?.key ?? '￿')
  return col.labels[a].localeCompare(col.labels[b], 'en', { numeric: true })
}

/**
 * Every row as scraped, after the dashboard's filters. Cells show the source text exactly; hovering a number
 * shows how it was read. Blank cells say "Not found"; cells left out of the math are struck in red with why.
 */
export function DataGrid({ profile, filters, height = 520, compact = false, picked = null, onPick }: { profile: TableProfile; filters: Filter[]; height?: number; compact?: boolean; picked?: number | null; onPick?: (row: number) => void }) {
  const [sort, setSort] = useState<Sort>(null)
  const [page, setPage] = useState(0)
  const cols = useMemo(() => profile.columns.filter((c) => !c.virtual), [profile])
  const excluded = useMemo(() => new Map(cols.map((c) => [c.index, new Map(c.excluded.map((e) => [e.row, e.reason]))])), [cols])

  const rows = useMemo(() => {
    const r = filterRows(profile, filters)
    if (sort) r.sort((a, b) => sort.dir * compareRows(profile.columns[sort.col], a, b))
    return r
  }, [profile, filters, sort])
  const pages = Math.max(1, Math.ceil(rows.length / PAGE))
  const current = Math.min(page, pages - 1)
  const slice = rows.slice(current * PAGE, current * PAGE + PAGE)

  const toggle = (col: number) => {
    setPage(0)
    setSort((s) => (s?.col !== col ? { col, dir: 1 } : s.dir === 1 ? { col, dir: -1 } : null))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className={`overflow-auto ${compact ? 'scrollbar-none' : 'rounded-panel border-2 border-ink'}`} style={{ maxHeight: compact ? height - 32 : height }} data-lenis-prevent>
        <table className="w-full min-w-max text-small">
          <thead className="sticky top-0 z-10 bg-surface">
            <tr className="border-b-2 border-ink">
              <th className="w-12 px-3 py-2 text-left font-mono text-micro font-normal text-ink-3">#</th>
              {cols.map((c) => (
                <th key={c.index} className={`px-3 py-2 font-medium ${isNumeric(c) ? 'text-right' : 'text-left'}`} aria-sort={sort?.col === c.index ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" onClick={() => toggle(c.index)} className="inline-flex items-center gap-1 hover:underline">
                    {c.label}
                    {sort?.col === c.index && <ChevronIcon className={sort.dir === 1 ? '-rotate-90' : 'rotate-90'} />}
                  </button>
                  <span className="block font-mono text-micro font-normal text-ink-3">{c.kind}{c.currency ? ` · ${c.currency}` : ''}{c.suffix ? ` · ${c.suffix}` : ''}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {slice.map((r) => (
              <tr key={r} className={`border-b border-line ${picked === r ? 'bg-signal-soft' : 'hover:bg-sunken'}`}>
                <td className="px-3 py-1.5 font-mono text-micro text-ink-3 tabular-nums">
                  {onPick ? (
                    <button type="button" onClick={() => onPick(r)} className="underline-offset-2 hover:underline" title="Why this row was kept">
                      {r + 1}
                    </button>
                  ) : (
                    r + 1
                  )}
                </td>
                {cols.map((c) => (
                  <Cell key={c.index} col={c} row={r} reason={excluded.get(c.index)?.get(r)} />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && <p className="p-6 text-center text-small text-ink-3">No rows match these filters.</p>}
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 font-mono text-micro text-ink-3">
          <span>
            Rows {current * PAGE + 1}–{Math.min(rows.length, (current + 1) * PAGE)} of {rows.length}
          </span>
          <button type="button" disabled={current === 0} onClick={() => setPage(current - 1)} className="rounded-control border-2 border-line px-2 py-0.5 text-ink hover:border-ink disabled:opacity-40">
            Previous
          </button>
          <button type="button" disabled={current >= pages - 1} onClick={() => setPage(current + 1)} className="rounded-control border-2 border-line px-2 py-0.5 text-ink hover:border-ink disabled:opacity-40">
            Next
          </button>
        </div>
      )}
    </div>
  )
}

function Cell({ col, row, reason }: { col: ColumnProfile; row: number; reason?: string }) {
  const raw = col.labels[row]
  const align = isNumeric(col) ? 'text-right font-mono tabular-nums' : ''
  if (!raw || isMissingText(raw)) {
    return <td className={`px-3 py-1.5 text-ink-3 italic ${align}`} title={raw ? `Marked “${raw}” in the source` : undefined}>Not found</td>
  }
  if (reason) {
    return (
      <td className={`px-3 py-1.5 ${align}`} title={`Left out of the numbers: ${reason}`}>
        <span className="line-through decoration-blocked decoration-2">{raw}</span>
      </td>
    )
  }
  if (col.kind === 'url') {
    const href = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`
    return (
      <td className="px-3 py-1.5">
        <a href={href} target="_blank" rel="noopener noreferrer" className="font-mono text-micro underline underline-offset-2 hover:text-ink-2">
          {domainOf(href)}
        </a>
      </td>
    )
  }
  const parsed = col.numbers?.[row]
  return (
    <td className={`px-3 py-1.5 ${align}`} title={parsed ? `Read as ${formatFor(col, parsed)}` : undefined}>
      {raw}
    </td>
  )
}
