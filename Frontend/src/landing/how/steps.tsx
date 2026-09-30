import type { ReactNode } from 'react'
import { chartFor } from '../../domain/charts.ts'
import { sampleByKey } from '../../domain/fixtures/index.ts'
import { METHOD, PERMISSION } from '../../product/meta.ts'
import { ArrowIcon, CheckIcon } from '../../ui/icons.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Strike } from '../../ui/Strike.tsx'
import type { Phase } from '../hero/timeline.ts'

// Every visual is drawn from the Internships sample, so the numbers are the sample's own.
const jobs = sampleByKey.jobs
const { plan, dataset } = jobs
const c = dataset.cleaning
const duplicates = c.rawRows - c.uniqueRows - c.rejected.length
const stipend = dataset.columns.find((col) => col.key === 'stipend')
const histogram = stipend ? chartFor(stipend, dataset.rows) : null

export type Step = { key: Phase; name: string; line: string; visual: (on: boolean) => ReactNode }

const tag = 'inline-flex h-7 items-center gap-1.5 rounded-control border-2 border-ink px-2 text-micro font-semibold'

export const STEPS: Step[] = [
  {
    key: 'ask',
    name: 'Ask',
    line: 'Say what you need in one sentence, or start from an example.',
    visual: () => (
      <div className="flex flex-col items-start gap-2">
        <p className="text-small text-ink">
          {jobs.request.text}
          <span aria-hidden className="ml-px inline-block h-[1.1em] w-0.5 translate-y-[0.2em] bg-ink" />
        </p>
        <span className={`${tag} bg-surface`}>
          Plan it <ArrowIcon />
        </span>
      </div>
    ),
  },
  {
    key: 'plan',
    name: 'Plan',
    line: 'AWDAX proposes columns, filters and sources, and says how it read unclear words. You edit it, then approve. Nothing runs before that.',
    visual: () => (
      <div className="flex flex-col items-start gap-2">
        <ul className="flex flex-wrap gap-1">
          {plan.columns.slice(0, 4).map((col) => (
            <li key={col.key} className="rounded-control bg-sunken px-1.5 py-0.5 text-micro text-ink">
              {col.label}
            </li>
          ))}
        </ul>
        <span className={`${tag} bg-signal`}>Approve plan</span>
      </div>
    ),
  },
  {
    key: 'run',
    name: 'Run',
    line: 'Each permitted source is read in its own lane. A source that can’t be read is skipped, with the reason.',
    visual: (on) => (
      <ul className="flex flex-col gap-1 font-mono text-micro text-ink">
        {plan.sources.map((s, i) => {
          const rows = dataset.rows.filter((r) => r.sourceIds[0] === s.id).length
          return (
            <li key={s.id} className="flex min-w-0 items-baseline justify-between gap-2">
              {s.permission === 'allowed' ? (
                <Mark ink={s.method} on={on} delay={i * 160} className="truncate" title={METHOD[s.method].label}>
                  {s.domain}
                </Mark>
              ) : (
                <Strike on={on} delay={i * 160} className="truncate text-ink-2">
                  {s.domain}
                </Strike>
              )}
              <span className="shrink-0 font-sans text-ink-3">
                {s.permission === 'allowed' ? `${rows} rows` : PERMISSION[s.permission]}
              </span>
            </li>
          )
        })}
      </ul>
    ),
  },
  {
    key: 'review',
    name: 'Review',
    line: 'Duplicates merge, rows that fail your filters are set aside, and values the sources disagree on are shown side by side.',
    visual: (on) => (
      <div className="flex flex-col gap-1">
        <p className="font-display font-wide text-h3 font-extrabold text-ink">
          {c.rawRows} raw → <Mark on={on}>{c.uniqueRows} unique</Mark>
        </p>
        <p className="text-micro text-ink-2">
          {duplicates} duplicates merged · {c.rejected.length} failed checks · {c.conflictRowIds.length}{' '}
          {c.conflictRowIds.length === 1 ? 'disagreement' : 'disagreements'}
        </p>
      </div>
    ),
  },
  {
    key: 'use',
    name: 'Use',
    line: 'A table, charts, and CSV or JSON export with every value’s receipt. Save it as a monitor to re-run on a schedule.',
    visual: () => (
      <div className="flex items-end justify-between gap-4">
        {histogram && (
          <div aria-hidden className="flex h-12 flex-1 items-end gap-0.5">
            {histogram.data.map((d) => (
              <span key={d.key} className="flex-1 bg-ink" style={{ height: `${(d.value / histogram.max) * 100}%` }} />
            ))}
          </div>
        )}
        <div className="flex shrink-0 gap-1">
          <span className={`${tag} bg-surface`}>CSV</span>
          <span className={`${tag} bg-surface`}>JSON</span>
          <span className={`${tag} bg-surface`}>
            <CheckIcon /> Monitor
          </span>
        </div>
      </div>
    ),
  },
]
