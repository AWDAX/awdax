import type { Column, Row, Source } from '../../domain/types.ts'
import { METHOD } from '../../product/meta.ts'
import { Mark } from '../../ui/Mark.tsx'
import { useArrived } from '../../ui/useArrived.ts'

type Props = {
  row: Row
  /** The source the row was read from (its first source). */
  source: Source
  columns: Column[]
  /** Column keys the row stream shows. Their quotes carry data-from, so TraceLayer can draw a line to the cell. */
  traced: readonly string[]
}

/**
 * The page AWDAX is reading for one row: its URL, the method, and the sentences the values came from,
 * each highlighted in its method's color as it is found. Structured pages read as JSON-LD.
 */
export function SourcePage({ row, source, columns, traced }: Props) {
  const arrived = useArrived()
  const quoted = columns.filter((c) => row.cells[c.key]?.quote)
  const url = columns.map((c) => row.cells[c.key]?.sourceUrl).find(Boolean) ?? `https://${source.domain}`
  const structured = source.method === 'structured'

  return (
    <article
      aria-label={`Source page being read: ${url.replace(/^https?:\/\//, '')}`}
      className="rounded-panel border-2 border-ink bg-surface"
    >
      <header className="flex items-center justify-between gap-3 border-b-2 border-ink px-4 py-2.5">
        <p className="min-w-0 truncate font-mono text-micro text-ink-2">{url.replace(/^https?:\/\//, '')}</p>
        <Mark ink={source.method} className="shrink-0 text-micro font-semibold text-ink">
          {METHOD[source.method].label}
        </Mark>
      </header>

      <div className={`flex flex-col p-4 sm:p-5 ${structured ? 'gap-2 font-mono text-small' : 'gap-3 text-body'}`}>
        {structured && <p className="font-mono text-micro text-ink-3">{'<script type="application/ld+json">'}</p>}
        {quoted.map((col, i) => {
          const cell = row.cells[col.key]
          const title = i === 0 && !structured
          return (
            <p key={col.key} className={title ? 'font-display text-h3 font-bold text-ink' : 'text-ink-2'}>
              <Mark
                ink={cell.method ?? source.method}
                on={arrived}
                delay={150 + i * 130}
                className="text-ink"
                data-from={traced.includes(col.key) ? `${row.id}:${col.key}` : undefined}
              >
                {cell.quote}
              </Mark>
            </p>
          )
        })}
      </div>
    </article>
  )
}
