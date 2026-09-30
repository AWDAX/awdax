import { useId, useState } from 'react'
import type { ReactNode } from 'react'
import type { Plan } from '../domain/types.ts'
import { Button } from '../ui/Button.tsx'
import { BanIcon, CheckIcon } from '../ui/icons.tsx'
import { Mark } from '../ui/Mark.tsx'
import { Strike } from '../ui/Strike.tsx'
import { METHOD, PERMISSION } from './meta.ts'
import { planSections } from './planItems.ts'
import type { PlanDensity } from './planItems.ts'

type Props = {
  plan: Plan
  /** Compact offers only the first unclear phrase, like PlanCard's compact density. */
  density?: PlanDensity
  /** Called with the edited plan when the user approves it. */
  onApprove?: (plan: Plan) => void
}

const heading = 'text-small font-semibold text-ink'
const focus = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink'

/**
 * The plan, editable before anything runs: drop optional columns, pick another reading of an unclear
 * phrase, see which sources will be skipped and why. Approving locks it; "Edit plan" unlocks it.
 * In a wide container: columns across the top, filters beside the readings, sources two by two.
 */
export function PlanEditor({ plan, density = 'full', onApprove }: Props) {
  const { interpretations } = planSections(plan, density)
  const [dropped, setDropped] = useState<ReadonlySet<string>>(new Set())
  const [readings, setReadings] = useState<Record<string, number>>({})
  const [approved, setApproved] = useState(false)

  const kept = plan.columns.filter((c) => !dropped.has(c.key))
  const allowed = plan.sources.filter((s) => s.permission === 'allowed')
  const toggle = (key: string) =>
    setDropped((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })

  const approve = () => {
    setApproved(true)
    onApprove?.({
      ...plan,
      columns: kept,
      interpretations: plan.interpretations.map((it) => {
        const pick = readings[it.phrase] ?? 0
        return pick === 0 ? it : { ...it, readAs: it.alternatives[pick - 1] }
      }),
    })
  }

  return (
    <section aria-label="Plan" className="rounded-panel border-2 border-ink bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink px-4 py-2.5 sm:px-5">
        <h3 className={heading}>Plan</h3>
        <p className="text-small text-ink-2" aria-live="polite">
          {kept.length} columns · {plan.filters.length} filters · {allowed.length} sources
        </p>
      </header>

      <div className="@container">
        <fieldset disabled={approved} className="grid gap-6 px-4 py-5 sm:px-5 @2xl:grid-cols-2 @2xl:gap-x-10">
          <Group title="Columns" note="Shaded columns are required. Select × to drop one." className="@2xl:col-span-2">
            <ul className="flex flex-wrap gap-2">
              {plan.columns.map((c) => {
                const off = dropped.has(c.key)
                return (
                  <li key={c.key}>
                    <button
                      type="button"
                      aria-pressed={!off}
                      disabled={c.required}
                      title={c.required ? 'Required column' : off ? `Add ${c.label} back` : `Drop ${c.label}`}
                      onClick={() => toggle(c.key)}
                      className={`inline-flex h-8 items-center gap-1.5 rounded-control border-2 px-2 text-small enabled:cursor-pointer enabled:hover:bg-sunken ${focus} ${
                        off ? 'border-line-strong text-ink-3' : c.required ? 'border-ink bg-sunken text-ink' : 'border-ink text-ink'
                      }`}
                    >
                      <Strike on={off} className="font-medium">
                        {c.label}
                      </Strike>
                      <span className="font-mono text-micro text-ink-3">{c.type}</span>
                      {c.required ? (
                        <span className="sr-only">(required)</span>
                      ) : (
                        <span aria-hidden className="font-mono text-small text-ink">
                          {off ? '+' : '×'}
                        </span>
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          </Group>

          <Group title="Filters">
            <ul className="flex flex-col gap-1">
              {plan.filters.map((f) => (
                <li key={f.label} className="flex gap-2 text-small text-ink-2">
                  <span aria-hidden className="mt-[0.7em] h-0.5 w-3 shrink-0 bg-ink" />
                  {f.label}
                </li>
              ))}
            </ul>
          </Group>

          <div className="flex min-w-0 flex-col gap-6">
            {interpretations.map((it) => (
              <Reading
                key={it.phrase}
                phrase={it.phrase}
                options={[it.readAs, ...it.alternatives]}
                value={readings[it.phrase] ?? 0}
                onChange={(i) => setReadings((prev) => ({ ...prev, [it.phrase]: i }))}
              />
            ))}
          </div>

          <Group title="Sources" className="@2xl:col-span-2">
            <ul className="grid gap-x-10 @2xl:grid-cols-2">
              {plan.sources.map((s) => {
                const skipped = s.permission !== 'allowed'
                return (
                  <li
                    key={s.id}
                    title={skipped ? s.note : undefined}
                    className="flex min-h-9 items-center justify-between gap-3 border-t border-line py-1.5 text-small"
                  >
                    <span className="inline-flex min-w-0 items-center gap-2 font-mono">
                      {skipped && <BanIcon className="shrink-0 text-blocked" />}
                      <span className="truncate">
                        {skipped ? <Strike className="text-ink-2">{s.domain}</Strike> : <Mark ink={s.method}>{s.domain}</Mark>}
                      </span>
                    </span>
                    <span className={`shrink-0 text-micro ${skipped ? 'font-semibold text-ink' : 'text-ink-3'}`}>
                      {skipped ? PERMISSION[s.permission] : METHOD[s.method].label}
                    </span>
                  </li>
                )
              })}
            </ul>
          </Group>
        </fieldset>
      </div>

      <footer className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-t-2 border-ink px-4 py-2.5 sm:px-5">
        {approved ? (
          <>
            <p className="inline-flex items-center gap-2 text-small font-semibold text-ink" role="status">
              <CheckIcon className="text-m-structured-line" />
              <Mark>Approved.</Mark> The run can start.
            </p>
            <Button variant="secondary" onClick={() => setApproved(false)}>
              Edit plan
            </Button>
          </>
        ) : (
          <>
            <p className="text-small text-ink-2">Nothing runs until you approve.</p>
            <Button onClick={approve}>Approve plan</Button>
          </>
        )}
      </footer>
    </section>
  )
}

type GroupProps = { title: string; note?: string; className?: string; children: ReactNode }

function Group({ title, note, className = '', children }: GroupProps) {
  return (
    <div className={`flex min-w-0 flex-col gap-2.5 ${className}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h4 className={heading}>{title}</h4>
        {note && <p className="text-micro text-ink-3">{note}</p>}
      </div>
      {children}
    </div>
  )
}

type ReadingProps = { phrase: string; options: string[]; value: number; onChange: (i: number) => void }

/** How an unclear phrase was read, with the other readings as choices. The chosen one is highlighted. */
function Reading({ phrase, options, value, onChange }: ReadingProps) {
  const name = useId()
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className={`${heading} mb-2.5`}>
        Read “{phrase}” as
      </legend>
      {options.map((opt, i) => (
        <label
          key={opt}
          className="flex cursor-pointer items-baseline gap-2.5 rounded-control text-small text-ink has-disabled:cursor-default has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-ink"
        >
          <input type="radio" name={name} checked={value === i} onChange={() => onChange(i)} className="peer sr-only" />
          <span aria-hidden className="size-3 shrink-0 translate-y-px rounded-full border-2 border-ink peer-checked:bg-ink" />
          <span>
            <Mark on={value === i}>{opt}</Mark>
            {i === 0 && <span className="ml-2 text-micro text-ink-3">AWDAX’s reading</span>}
          </span>
        </label>
      ))}
    </fieldset>
  )
}
