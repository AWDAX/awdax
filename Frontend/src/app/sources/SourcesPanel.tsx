import { timeAgo } from '../../api/dates.ts'
import type { RunReport } from '../../analytics/runReport.ts'
import type { SourceView, Visit } from './buildSources.ts'
import { SourceCard } from './SourceCard.tsx'

type Props = { sources: SourceView[]; report: RunReport | null; visits: Visit[] }

/**
 * Where the data came from: every website that gave rows or was checked, with exact row counts and the
 * backend's own scores; rejected sites struck through with the reason; and the pages read, in order.
 */
export function SourcesPanel({ sources, report, visits }: Props) {
  const used = sources.filter((s) => s.state !== 'rejected')
  const rejected = sources.filter((s) => s.state === 'rejected')
  const rows = used.reduce((n, s) => n + s.rows, 0)

  return (
    <section aria-label="Sources" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="font-display text-h3 font-extrabold">Where the data came from</h3>
          <p className="text-small text-ink-2">
            {rows > 0
              ? `${used.filter((s) => s.rows > 0).length} ${used.filter((s) => s.rows > 0).length === 1 ? 'website' : 'websites'} gave ${rows.toLocaleString('en-IN')} rows`
              : `${used.length} ${used.length === 1 ? 'website' : 'websites'} checked so far; rows appear after the first pass`}
            {rejected.length + (report?.rejectedMore ?? 0) > 0 && ` · ${rejected.length + (report?.rejectedMore ?? 0)} rejected`}
            {report?.status && ` · discovery ${report.status}`}
          </p>
        </div>
        {report?.expectedRows !== undefined && (
          <p className="font-mono text-micro text-ink-3">
            Expected ~{report.expectedRows} · extracted {report.actualRows ?? rows}
          </p>
        )}
      </div>

      {used.length === 0 ? (
        <p className="rounded-panel border-2 border-dashed border-line-strong p-6 text-center text-small text-ink-2">
          No sources yet. They appear here as AWDAX finds and reads them, and in full after the first pass.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {used.map((s) => (
            <SourceCard key={s.site} s={s} />
          ))}
        </ul>
      )}

      {rejected.length > 0 && (
        <div>
          <h4 className="text-small font-semibold">Rejected</h4>
          <ul className="mt-1.5 flex flex-col gap-1.5 text-small">
            {rejected.map((s) => (
              <li key={s.site} className="flex flex-wrap gap-x-2">
                <span className="line-through decoration-blocked decoration-2">{s.title}</span>
                <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-mono text-micro text-ink-3 underline underline-offset-2">
                  {s.site}
                </a>
                <span className="text-ink-2">{s.reason}</span>
              </li>
            ))}
            {report?.rejectedMore ? <li className="text-micro text-ink-3">…and {report.rejectedMore} more that the backend didn’t list.</li> : null}
          </ul>
        </div>
      )}

      {(report?.strategies.length || visits.length) ? (
        <div className="grid gap-4 md:grid-cols-2">
          {report?.strategies.length ? (
            <details className="rounded-panel border-2 border-line p-3">
              <summary className="cursor-pointer text-small font-semibold">How the sources were found ({report.strategies.length} searches)</summary>
              <ul className="mt-2 flex flex-col gap-1 font-mono text-micro text-ink-2">
                {report.strategies.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
            </details>
          ) : null}
          {visits.length > 0 && (
            <details className="rounded-panel border-2 border-line p-3">
              <summary className="cursor-pointer text-small font-semibold">Pages read ({visits.length})</summary>
              <ol className="mt-2 flex max-h-56 flex-col gap-1 overflow-y-auto font-mono text-micro text-ink-2" data-lenis-prevent>
                {[...visits].reverse().map((v, i) => (
                  <li key={`${v.at}-${i}`} className="flex gap-2">
                    <span className="shrink-0 text-ink-3">{timeAgo(v.at)}</span>
                    <span className="truncate" title={v.source}>{v.source}</span>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      ) : null}
    </section>
  )
}
