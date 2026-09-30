import type { ReactNode } from 'react'
import { formatCaptured, formatValue } from '../domain/format.ts'
import type { Cell, Column, Method } from '../domain/types.ts'
import { Mark } from '../ui/Mark.tsx'
import { useArrived } from '../ui/useArrived.ts'
import { METHOD } from './meta.ts'

type Props = {
  column: Column
  cell: Cell
  /** What the row is, e.g. "Frontend Developer Intern · Nimbus Labs". */
  rowLabel: string
  /** The row's source method, for cells that don't record their own. */
  fallbackMethod: Method
}

const CONFIDENCE = { high: 'High', medium: 'Medium: read from loosely formatted text', low: 'Low' } as const

const url = (u: string) => u.replace(/^https?:\/\//, '')

/**
 * The receipt for one value: where it was found, when, how, and the exact sentence it was read from,
 * highlighted in the method's color. Key it by cell so the highlight sweeps in again on each new cell.
 */
export function CellReceipt({ column, cell, rowLabel, fallbackMethod }: Props) {
  const arrived = useArrived()
  const method = cell.method ?? fallbackMethod
  const found = cell.status !== 'not_found'

  return (
    <article className="flex flex-col rounded-panel border-2 border-ink bg-surface">
      <header className="border-b-2 border-ink px-4 py-3 sm:px-5">
        <p className="text-micro text-ink-3">
          Receipt · <span className="text-ink-2">{column.label}</span>
        </p>
        <p className="truncate text-small text-ink-2">{rowLabel}</p>
      </header>

      <div className="flex flex-col gap-5 px-4 py-5 sm:px-5">
        <p className="font-display font-wide text-h2 font-extrabold text-ink">
          {found ? formatValue(cell.value, column) : 'Not found'}
        </p>

        {!found ? (
          <p className="max-w-[40ch] text-body text-ink-2">
            No permitted source had this value. AWDAX leaves the cell empty and says so, instead of guessing.
          </p>
        ) : (
          <>
            <div className="flex flex-col gap-2">
              <p className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <span className="min-w-0 truncate font-mono text-micro text-ink-2">{url(cell.sourceUrl ?? '')}</span>
                <Mark ink={method} className="shrink-0 text-micro font-semibold text-ink">
                  {METHOD[method].label}
                </Mark>
              </p>
              <blockquote className={`border-l-2 border-ink pl-3 text-body text-ink ${method === 'structured' ? 'font-mono text-small' : ''}`}>
                <Mark ink={method} on={arrived} delay={200}>
                  {cell.quote}
                </Mark>
              </blockquote>
            </div>

            <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-small">
              <Meta term="Captured">{cell.capturedAt ? formatCaptured(cell.capturedAt) : '—'}</Meta>
              <Meta term="Confidence">{cell.confidence ? CONFIDENCE[cell.confidence] : '—'}</Meta>
            </dl>
          </>
        )}

        {cell.status === 'conflict' && cell.alternatives && (
          <div className="flex flex-col gap-2 border-t-2 border-ink pt-4">
            <p className="text-small font-semibold text-ink">Another source says</p>
            {cell.alternatives.map((alt) => (
              <div key={alt.sourceUrl} className="flex flex-col gap-1">
                <p className="text-body font-semibold text-ink">{formatValue(alt.value, column)}</p>
                <p className="truncate font-mono text-micro text-ink-2">{url(alt.sourceUrl)}</p>
                <blockquote className="border-l-2 border-line-strong pl-3 text-small text-ink-2">{alt.quote}</blockquote>
              </div>
            ))}
            <p className="text-micro text-ink-3">
              Kept by rule: the most recent value, then the one more sources agree on. You can override it.
            </p>
          </div>
        )}
      </div>
    </article>
  )
}

function Meta({ term, children }: { term: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-3">{term}</dt>
      <dd className="text-ink">{children}</dd>
    </>
  )
}
