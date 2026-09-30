import type { ReactNode } from 'react'
import { domainOf } from '../../domain/format.ts'
import { apiDate } from '../../api/dates.ts'
import type { LiveState } from '../../api/useLiveStream.ts'
import { CallChip } from '../../ui/micro/CallChip.tsx'
import { ThoughtLine } from '../../ui/micro/ThoughtLine.tsx'
import { phaseLabel, STEPS, stepStatus, WORKING } from './phases.ts'

type Props = {
  live: LiveState
  /** Re-arms tracking after an error: live off, then on (PATCH /live). */
  onRetry: () => void
  /** Under the steps: the websites involved. */
  footer?: ReactNode
}

function ahead(iso: string | null | undefined): string {
  const d = apiDate(iso)
  if (!d) return ''
  const diff = d.getTime() - Date.now()
  if (diff < 60_000) return 'next batch due'
  const min = Math.round(diff / 60_000)
  return min < 60 ? `next batch in ${min} min` : `next batch in ${Math.round(min / 60)} h`
}

/**
 * What the backend is doing right now: the phase, the page being read, batch timing and the latest pipeline
 * steps. Rows arrive over the WebSocket; if that cannot open, the event stream and polling take over.
 */
export function LiveRun({ live, onRetry, footer }: Props) {
  const s = live.status
  const working = live.liveEnabled && WORKING.includes(s.phase ?? 'idle')
  const hasData = live.rowsTotal > 0 || !!live.dataset
  const source = s.current_source ? (/^https?:/i.test(s.current_source) ? domainOf(s.current_source) : s.current_source) : undefined
  const label = phaseLabel(s, live.liveEnabled)
  const batchMin = s.batch_seconds ? Math.max(1, Math.round(s.batch_seconds / 60)) : 0
  const everyMin = s.interval_seconds ? Math.max(1, Math.round(s.interval_seconds / 60)) : 0
  const events = (live.events ?? []).slice(-4)

  return (
    <section aria-label="Live run" aria-live="polite" className="rounded-panel border-2 border-ink p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <ThoughtLine
          label={label}
          doneLabel={s.phase === 'error' ? label : `${label} · ${live.rowsTotal.toLocaleString('en-IN')} rows`}
          working={working}
          steps={working && s.detail ? [s.detail] : undefined}
          collapsible={false}
          showTimer={false}
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
      <ul className="mt-3 flex flex-wrap gap-2">
        {STEPS.map((step, i) => {
          const status = live.liveEnabled || i === 0 ? stepStatus(s, i, hasData) : hasData ? 'done' : 'idle'
          return (
            <li key={step.phase}>
              <CallChip
                icon={step.icon}
                name={step.name}
                argument={status === 'running' ? source : undefined}
                status={status}
                expectedMs={step.expectedMs}
                showTimer={status === 'running'}
                onRetry={status === 'error' ? onRetry : undefined}
              />
            </li>
          )
        })}
      </ul>
      {events.length > 0 && (
        <ol className="mt-3 flex flex-col gap-1 border-t border-line pt-3 font-mono text-micro text-ink-2">
          {events.map((event) => (
            <li key={event.id}>{event.detail || event.phase}</li>
          ))}
        </ol>
      )}
      {footer && <div className="mt-3 border-t border-line pt-3">{footer}</div>}
      {s.phase === 'error' && s.detail && (
        <p className="mt-3 rounded-control bg-sunken p-2 font-mono text-micro break-words text-ink-2">{s.detail}</p>
      )}
    </section>
  )
}
