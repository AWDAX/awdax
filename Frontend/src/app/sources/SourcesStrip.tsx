import type { SourceView } from './buildSources.ts'

/**
 * The websites of a run at a glance, for the live run card: the one being read now in signal yellow, the ones
 * that gave rows with their exact counts, rejected ones struck through.
 */
export function SourcesStrip({ sources, onOpen }: { sources: SourceView[]; onOpen?: () => void }) {
  if (sources.length === 0) return null
  const shown = sources.slice(0, 8)
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 font-mono text-micro text-ink-3">Sources</span>
      {shown.map((s) => (
        <a
          key={s.site}
          href={s.url}
          target="_blank"
          rel="noopener noreferrer"
          title={`${s.title}${s.reason ? ` · rejected: ${s.reason}` : ''}`}
          className={`inline-flex items-center gap-1.5 rounded-control border-2 px-2 py-0.5 font-mono text-micro ${
            s.state === 'reading' ? 'border-ink bg-signal' : s.state === 'rejected' ? 'border-line text-ink-3' : s.rows ? 'border-ink' : 'border-line text-ink-2'
          }`}
        >
          {s.state === 'reading' && <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-ink" />}
          <span className={s.state === 'rejected' ? 'line-through decoration-blocked decoration-2' : ''}>{s.site}</span>
          {s.rows > 0 && <span className="text-ink-2">{s.rows.toLocaleString('en-IN')}</span>}
        </a>
      ))}
      {sources.length > shown.length && <span className="font-mono text-micro text-ink-3">+{sources.length - shown.length}</span>}
      {onOpen && (
        <button type="button" onClick={onOpen} className="ml-1 text-small underline underline-offset-2 hover:text-ink-2">
          Details
        </button>
      )}
    </div>
  )
}
