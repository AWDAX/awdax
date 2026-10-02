import { useState } from 'react'
import type { SourceView } from './buildSources.ts'
import { topSources } from './topSources.ts'

const TOP = 3

/**
 * The websites of a run at a glance, for the live run card: only the top three (the one being read now in signal
 * yellow, then the ones that gave the most rows), then "+N more". Details opens the full Sources tab once there
 * is a dashboard; before that it lists every site here.
 */
export function SourcesStrip({ sources, onOpen }: { sources: SourceView[]; onOpen?: () => void }) {
  const [all, setAll] = useState(false)
  if (sources.length === 0) return null
  const ranked = topSources(sources)
  const shown = all ? ranked : ranked.slice(0, TOP)
  const hidden = ranked.length - shown.length
  const canExpand = !onOpen && ranked.length > TOP
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
      {(onOpen || canExpand) && (
        <button
          type="button"
          onClick={onOpen ?? (() => setAll((a) => !a))}
          aria-expanded={onOpen ? undefined : all}
          className="ml-1 text-small underline underline-offset-2 hover:text-ink-2"
        >
          {!onOpen && all ? 'Show less' : 'Details'}
        </button>
      )}
    </div>
  )
}
