import { toNumber } from '../../analytics/decimal.ts'
import { formatDec } from '../../analytics/format.ts'
import { methodOf } from './buildSources.ts'
import type { SourceState, SourceView } from './buildSources.ts'

const STATE: Record<SourceState, { label: string; cls: string }> = {
  reading: { label: 'Reading now', cls: 'border-ink bg-signal' },
  used: { label: 'Rows used', cls: 'border-ink' },
  validated: { label: 'Validated, no rows yet', cls: 'border-line text-ink-2' },
  visited: { label: 'Visited', cls: 'border-line text-ink-2' },
  rejected: { label: 'Rejected', cls: 'border-blocked text-blocked' },
}

// Method highlighter fills: each colour has one meaning across AWDAX (DESIGN_SYSTEM "Highlighters").
const TONE = {
  structured: 'bg-m-structured',
  content: 'bg-m-content',
  rendered: 'bg-m-rendered',
  ai: 'bg-m-ai',
} as const

function Score({ label, value }: { label: string; value?: number }) {
  if (value === undefined) return null
  return (
    <span className="flex items-center gap-1.5" title={`${label}: ${value} out of 10, as the backend scored it`}>
      <span className="text-ink-3">{label}</span>
      <span className="flex h-1.5 w-12 overflow-hidden rounded-sm bg-sunken" aria-hidden>
        <span className="bg-ink" style={{ width: `${value * 10}%` }} />
      </span>
      <span className="font-mono tabular-nums">{value}/10</span>
    </span>
  )
}

/** One website: what it gave (exact rows and share), how it was read, how it scored and what to watch for. */
export function SourceCard({ s }: { s: SourceView }) {
  const r = s.report
  const method = methodOf(r?.access)
  const state = STATE[s.state]
  return (
    <li className={`flex min-w-0 flex-col gap-2 rounded-panel border-2 p-3 ${s.state === 'reading' ? 'border-ink bg-signal-soft/40' : 'border-ink'}`}>
      <div className="flex items-start gap-2">
        {r && <span className="grid size-6 shrink-0 place-items-center rounded-control border-2 border-ink font-mono text-micro font-medium">{r.rank}</span>}
        <div className="min-w-0 flex-1">
          <p className="truncate font-semibold" title={s.title}>
            {s.title}
          </p>
          <a href={s.url} target="_blank" rel="noopener noreferrer" className="block truncate font-mono text-micro text-ink-2 underline decoration-line-strong underline-offset-2 hover:decoration-ink" title={s.url}>
            {s.url}
          </a>
        </div>
        <span className={`shrink-0 rounded-control border-2 px-2 py-0.5 text-micro font-medium ${state.cls}`}>{state.label}</span>
      </div>

      {s.rows > 0 && (
        <div className="flex items-center gap-2 text-small">
          <span className="flex h-2 flex-1 overflow-hidden rounded-sm bg-sunken" aria-hidden>
            <span className="bg-series" style={{ width: `${s.share ? toNumber(s.share) : 0}%` }} />
          </span>
          <span className="font-mono tabular-nums">
            {s.rows.toLocaleString('en-IN')} rows{s.share ? ` · ${formatDec(s.share)}%` : ''}
          </span>
        </div>
      )}

      {r && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-micro">
          <Score label="Quality" value={r.quality} />
          <Score label="Authority" value={r.authority} />
          <Score label="Relevance" value={r.relevance} />
        </div>
      )}

      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-micro">
        {r?.access && (
          <>
            <dt className="text-ink-3">Read as</dt>
            <dd>{method.tone ? <span className={`rounded-sm px-1 text-ink ${TONE[method.tone]}`}>{method.label}</span> : method.label}</dd>
          </>
        )}
        {r?.format && (
          <>
            <dt className="text-ink-3">Format</dt>
            <dd>{r.format.replace(/_/g, ' ')}{r.pagesInspected ? ` · ${r.pagesInspected} pages inspected` : ''}</dd>
          </>
        )}
        {s.fill && (
          <>
            <dt className="text-ink-3">Filled</dt>
            <dd>
              <span className="font-mono">{s.fill.fillRate}%</span> of cells · {s.fill.status}
              {s.fill.summary ? ` · ${s.fill.summary}` : ''}
            </dd>
          </>
        )}
        {r?.likelyFields.length ? (
          <>
            <dt className="text-ink-3">Fields</dt>
            <dd className="font-mono">{r.likelyFields.join(', ')}</dd>
          </>
        ) : null}
        {r?.notes && (
          <>
            <dt className="text-ink-3">Notes</dt>
            <dd className="text-ink-2">{r.notes}</dd>
          </>
        )}
        {s.rankReasons && s.rankReasons.length > 0 ? (
          <>
            <dt className="text-ink-3">Ranked because</dt>
            <dd className="text-ink-2">{s.rankReasons.slice(0, 3).join(' · ')}</dd>
          </>
        ) : null}
        {s.origin ? (
          <>
            <dt className="text-ink-3">Found via</dt>
            <dd>{s.origin.replace(/_/g, ' ')}</dd>
          </>
        ) : null}
        {(s.deepAccepted || s.deepNotes?.length) ? (
          <>
            <dt className="text-ink-3">Interactive pass</dt>
            <dd className="text-ink-2">
              {s.deepAccepted ? `+${s.deepAccepted.toLocaleString('en-IN')} rows` : 'No extra rows'}
              {s.deepNotes?.length ? ` · ${s.deepNotes.slice(0, 3).join(' · ')}` : ''}
            </dd>
          </>
        ) : null}
        {r?.blockers.length ? (
          <>
            <dt className="text-ink-3">Watch for</dt>
            <dd className="text-blocked">{r.blockers.join('; ')}</dd>
          </>
        ) : null}
      </dl>
    </li>
  )
}
