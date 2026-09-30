import { Mark } from '../../ui/Mark.tsx'
import { PHASES } from './timeline.ts'
import type { Phase } from './timeline.ts'

const LABEL: Record<Phase, string> = { ask: 'Ask', plan: 'Plan', run: 'Run', review: 'Review', use: 'Use' }

/** Ask → Plan → Run → Review → Use, the current step highlighted. Narrow screens show only the current one. */
export function StepRail({ phase }: { phase: Phase }) {
  const current = PHASES.indexOf(phase)
  return (
    <ol aria-label="Steps" className="flex items-baseline gap-5">
      {PHASES.map((p, i) => {
        const state = i === current ? 'font-semibold text-ink' : i < current ? 'text-ink-2' : 'text-ink-3'
        return (
          <li
            key={p}
            aria-current={i === current ? 'step' : undefined}
            className={`items-baseline gap-1.5 text-small ${state} ${i === current ? 'inline-flex' : 'hidden md:inline-flex'}`}
          >
            <span className="font-mono text-micro text-ink-3">{String(i + 1).padStart(2, '0')}</span>
            <Mark on={i === current}>{LABEL[p]}</Mark>
          </li>
        )
      })}
    </ol>
  )
}
