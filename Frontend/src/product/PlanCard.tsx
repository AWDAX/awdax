import type { ReactNode } from 'react'
import type { Plan, Source, SourceStage } from '../domain/types.ts'
import { BanIcon, CheckIcon } from '../ui/icons.tsx'
import { buttonClass } from '../ui/buttonClass.ts'
import { Mark } from '../ui/Mark.tsx'
import { METHOD, PERMISSION, STAGE } from './meta.ts'
import { planSections } from './planItems.ts'
import type { PlanDensity } from './planItems.ts'

type Props = {
  plan: Plan
  density?: PlanDensity
  /** Items shown so far, in reveal order (see planItems.ts). Everything by default. */
  revealed?: number
  approved: boolean
  /** Shows the approve button mid-press, for the landing replay. */
  pressing?: boolean
  /** Per-source progress once a run has started. */
  stages?: Partial<Record<string, SourceStage>>
  rowsFound?: Partial<Record<string, number>>
  onApprove?: () => void
}

// Each item fades up when its turn comes. Reduced motion drops the transition (index.css).
const reveal = (shown: boolean) =>
  `transition-[opacity,translate] duration-700 ease-soft ${shown ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-1.5'}`

const label = 'font-sans text-small font-semibold text-ink'

function Group({ title, shown, className = 'flex', children }: { title: string; shown: boolean; className?: string; children: ReactNode }) {
  return (
    <div className={`flex-col gap-2 ${className}`}>
      <h4 className={`${label} ${reveal(shown)}`}>{title}</h4>
      {children}
    </div>
  )
}

export function PlanCard({
  plan,
  density = 'full',
  revealed = Infinity,
  approved,
  pressing = false,
  stages,
  rowsFound,
  onApprove,
}: Props) {
  const s = planSections(plan, density)
  const start = {
    columns: 0,
    filters: s.columns.length,
    interpretations: s.columns.length + s.filters.length,
    sources: s.columns.length + s.filters.length + s.interpretations.length,
  }
  const shown = (i: number) => i < revealed
  const planReady = revealed >= start.sources + s.sources.length
  // Compact plans keep phones short: columns and sources stay, filters and readings wait for wider screens.
  const secondary = density === 'compact' ? 'hidden sm:flex' : 'flex'

  return (
    <section aria-label="Plan" className="flex flex-col gap-5">
      <header className="flex min-h-10 items-center justify-between gap-3">
        <h3 className={label}>Plan</h3>
        <ApproveState approved={approved} ready={planReady} pressing={pressing} onApprove={onApprove} />
      </header>

      <Group title="Columns" shown={shown(start.columns)}>
        <ul className="flex flex-wrap gap-1.5">
          {s.columns.map((c, i) => (
            <li
              key={c.key}
              className={`inline-flex h-7 items-center gap-1.5 rounded-control border border-line bg-canvas px-2 text-small ${reveal(shown(start.columns + i))}`}
            >
              <span className="font-medium text-ink">{c.label}</span>
              <span className="font-mono text-micro text-ink-3">{c.type}</span>
              {c.required && <span className="sr-only">(required)</span>}
            </li>
          ))}
        </ul>
      </Group>

      {s.filters.length > 0 && (
        <Group title="Filters" shown={shown(start.filters)} className={secondary}>
          <ul className="flex flex-col gap-1">
            {s.filters.map((f, i) => (
              <li key={f.label} className={`flex gap-2 text-small text-ink-2 ${reveal(shown(start.filters + i))}`}>
                <span aria-hidden className="mt-[0.7em] h-px w-3 shrink-0 bg-line-strong" />
                {f.label}
              </li>
            ))}
          </ul>
        </Group>
      )}

      {s.interpretations.length > 0 && (
        <Group title="Read as" shown={shown(start.interpretations)} className={secondary}>
          <ul className="flex flex-col gap-2">
            {s.interpretations.map((it, i) => (
              <li key={it.phrase} className={`text-small text-ink-2 ${reveal(shown(start.interpretations + i))}`}>
                <span className="font-medium text-ink">“{it.phrase}”</span> means {it.readAs.charAt(0).toLowerCase()}
                {it.readAs.slice(1)}.{' '}
                <span className="text-ink-3">
                  {it.alternatives.length} other {it.alternatives.length === 1 ? 'reading' : 'readings'}
                </span>
              </li>
            ))}
          </ul>
        </Group>
      )}

      <Group title="Sources" shown={shown(start.sources)}>
        <ul className="flex flex-col">
          {s.sources.map((src, i) => (
            <SourceLine
              key={src.id}
              source={src}
              stage={stages?.[src.id]}
              rows={rowsFound?.[src.id] ?? 0}
              className={reveal(shown(start.sources + i))}
            />
          ))}
        </ul>
      </Group>
    </section>
  )
}

function ApproveState({ approved, ready, pressing, onApprove }: { approved: boolean; ready: boolean; pressing: boolean; onApprove?: () => void }) {
  if (approved) {
    return (
      <span className="inline-flex items-center gap-1.5 text-small font-medium text-ink">
        <CheckIcon className="text-m-structured-line" /> Approved
      </span>
    )
  }
  const cls = buttonClass('primary', 'md', pressing ? 'scale-97 bg-ink! text-signal!' : '')
  return (
    <span className={`inline-flex ${reveal(ready)}`}>
      {onApprove ? (
        <button type="button" onClick={onApprove} className={cls}>
          Approve plan
        </button>
      ) : (
        // On the landing page the replay approves by itself, so this is a picture of the button, not a control.
        <span aria-hidden className={cls}>
          Approve plan
        </span>
      )}
    </span>
  )
}

function SourceLine({ source, stage, rows, className }: { source: Source; stage?: SourceStage; rows: number; className: string }) {
  const skipped = source.permission !== 'allowed'
  return (
    <li className={`grid grid-cols-[1rem_minmax(0,1fr)_auto] items-start gap-x-2 border-t border-line py-2 first:border-t-0 ${className}`}>
      {skipped ? <BanIcon className="mt-0.5 text-blocked" /> : <span aria-hidden />}
      <div className="min-w-0">
        {skipped ? (
          // Red pen: a source AWDAX will not read, struck through, with the reason underneath.
          <p className="truncate font-mono text-small text-ink-2 line-through decoration-blocked decoration-2">
            {source.domain}
          </p>
        ) : (
          <p className="truncate font-mono text-small text-ink">
            <Mark ink={source.method}>{source.domain}</Mark>
          </p>
        )}
        <p className="text-micro text-ink-3">
          {skipped ? (source.note ?? PERMISSION[source.permission]) : METHOD[source.method].label}
        </p>
      </div>
      <StageBadge stage={skipped && stage ? 'skipped' : stage} rows={rows} />
    </li>
  )
}

function StageBadge({ stage, rows }: { stage?: SourceStage; rows: number }) {
  if (!stage) return null
  const busy = stage === 'fetching' || stage === 'extracting'
  const tone = stage === 'skipped' || stage === 'failed' ? 'text-blocked' : stage === 'done' ? 'text-ink' : 'text-ink-2'
  return (
    <span className={`inline-flex items-center gap-1.5 pt-0.5 text-micro font-medium whitespace-nowrap ${tone}`}>
      {busy && <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-ink" />}
      {stage === 'done' ? `${rows} ${rows === 1 ? 'row' : 'rows'}` : STAGE[stage]}
    </span>
  )
}
