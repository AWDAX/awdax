import { useState } from 'react'
import type { ReactNode } from 'react'
import { domainOf } from '../../domain/format.ts'
import { apiDate, apiTime } from '../../api/dates.ts'
import type { LiveState } from '../../api/useLiveStream.ts'
import { ReplayIcon } from '../../ui/icons.tsx'
import { ThoughtLine } from '../../ui/micro/ThoughtLine.tsx'
import { phaseLabel } from './phases.ts'
import { runTrace } from './runTrace.ts'

type Props = {
  live: LiveState
  /** Re-arms tracking after an error: live off, then on (PATCH /live). */
  onRetry: () => void
  /** Under the steps: the websites involved. */
  footer?: ReactNode
  /** When the chat's first run started, for the clock (a live chat). */
  startedAt?: string
  /** The run's own elapsed seconds (a replay): the clock shows this instead of ticking. */
  elapsedSec?: number
}

function ahead(iso: string | null | undefined): string {
  const d = apiDate(iso)
  if (!d) return ''
  const diff = d.getTime() - Date.now()
  if (diff < 60_000) return 'next batch due'
  const min = Math.round(diff / 60_000)
  return min < 60 ? `next batch in ${min} min` : `next batch in ${Math.round(min / 60)} h`
}

// The first pass's clock runs from the chat's start only while this page watches that pass; a later re-check, or a
// run that finished before the page opened, shows no time rather than a wrong one.
type Clock = 'none' | 'first' | 'settled' | 'later'

/**
 * What the backend is doing right now, as one ThoughtLine: the phase shimmering with a live clock, the steps so far
 * beneath it (the current one naming the site it reads), settling to "Finished in …" or "Up to date". Then batch
 * timing, the latest pipeline lines and the sites. Rows arrive over the WebSocket, or the event stream and polling.
 */
export function LiveRun({ live, onRetry, footer, startedAt, elapsedSec }: Props) {
  const s = live.status
  const hasData = live.rowsTotal > 0 || !!live.dataset
  const site = s.current_source ? (/^https?:/i.test(s.current_source) ? domainOf(s.current_source) : s.current_source) : undefined
  const label = phaseLabel(s, live.liveEnabled)
  const { busy, steps, waiting } = runTrace(s, live.liveEnabled, hasData, site)
  const batchMin = s.batch_seconds ? Math.max(1, Math.round(s.batch_seconds / 60)) : 0
  const everyMin = s.interval_seconds ? Math.max(1, Math.round(s.interval_seconds / 60)) : 0
  const events = (live.events ?? []).slice(-4)
  const failed = s.phase === 'error'

  const [clock, setClock] = useState<Clock>(busy && !hasData ? 'first' : 'none')
  if (clock === 'none' && busy && !hasData) setClock('first')
  else if (clock === 'first' && !busy) setClock('settled')
  else if (clock === 'settled' && busy) setClock('later')
  const origin = startedAt ? apiTime(startedAt) : NaN
  const timed = !failed && (elapsedSec != null || (Number.isFinite(origin) && (clock === 'first' || clock === 'settled')))

  return (
    <section aria-label="Live run" className="rounded-panel border-2 border-ink p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <ThoughtLine
          label={label}
          doneLabel={timed ? 'Finished in' : label}
          working={busy || waiting}
          steps={steps}
          elapsed={elapsedSec}
          startedAt={Number.isFinite(origin) ? origin : undefined}
          showTimer={timed}
          fontSize={15}
          className="min-w-0 max-w-full"
        />
        <span className="font-mono text-micro text-ink-3">
          {live.rowsTotal.toLocaleString('en-IN')} rows
          {batchMin ? ` · ${batchMin} min batches` : ''}
          {everyMin && s.phase === 'sleep' ? ` · every ${everyMin} min` : ''}
          {s.rows_added_last_cycle ? ` · +${s.rows_added_last_cycle} last batch` : ''}
          {live.partialAdded ? ` · ${live.partialAdded.toLocaleString('en-IN')} partial held` : ''}
          {ahead(s.next_cycle_at) ? ` · ${ahead(s.next_cycle_at)}` : ''}
          {!live.connected && ' · reconnecting'}
        </span>
      </div>
      {events.length > 0 && (
        <ol className="mt-3 flex flex-col gap-1 border-t border-line pt-3 font-mono text-micro text-ink-2">
          {events.map((event) => (
            <li key={event.id}>{event.detail || event.phase}</li>
          ))}
        </ol>
      )}
      {footer && <div className="mt-3 border-t border-line pt-3">{footer}</div>}
      {failed && (
        <div className="mt-3 flex flex-wrap items-start gap-3 rounded-control bg-sunken p-2">
          {s.detail && <p className="min-w-0 flex-1 font-mono text-micro break-words text-ink-2">{s.detail}</p>}
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-control border-2 border-ink bg-surface px-3 text-small font-semibold transition-colors duration-300 ease-soft hover:bg-ink hover:text-on-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            <ReplayIcon /> Try again
          </button>
        </div>
      )}
    </section>
  )
}
