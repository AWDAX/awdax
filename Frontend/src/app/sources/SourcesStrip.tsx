import type { SourceView } from './buildSources.ts'
import { topSources } from './topSources.ts'

const TOP = 3

type Props = {
  sources: SourceView[]
  /** Shows the full source list: the panel under the run, or the dashboard's Sources tab. */
  onOpen?: () => void
  /** The panel under the run is showing, so the button hides it. */
  open?: boolean
}

/**
 * The websites of a run at a glance, for the live run card: only the top three (the one being read now in signal
 * yellow, then the ones that gave the most rows), then "+N more". Every site, with what was found on each, is one
 * click away under Details, so the page never lists the sources twice.
 */
export function SourcesStrip({ sources, onOpen, open = false }: Props) {
  if (sources.length === 0) return null
  const ranked = topSources(sources)
  const shown = ranked.slice(0, TOP)
  const hidden = ranked.length - shown.length
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
      {hidden > 0 && <span className="font-mono text-micro text-ink-3">+{hidden} more</span>}
      {onOpen && (
        <button type="button" onClick={onOpen} aria-expanded={open} className="ml-1 text-small underline underline-offset-2 hover:text-ink-2">
          {open ? 'Hide details' : 'Details'}
        </button>
      )}
    </div>
  )
}
