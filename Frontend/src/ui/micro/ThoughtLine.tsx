import { useEffect, useRef, useState } from 'react'
import { m, useReducedMotion } from 'motion/react'
import { ChevronIcon } from '../appIcons.tsx'
import { CheckIcon } from '../icons.tsx'
import { EASE_SOFT } from '../motion.ts'

export type ThoughtLineProps = {
  label?: string
  doneLabel?: string
  steps?: string[]
  working?: boolean
  /** Fixed elapsed seconds (e.g. loaded from history). Ticks up on its own when omitted. */
  elapsed?: number
  showTimer?: boolean
  collapsible?: boolean
  onSettle?: (seconds: number) => void
  className?: string
}

function formatSeconds(s: number) {
  if (s < 60) return `${s.toFixed(1)}s`
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
}

/** The live "working" line in a chat: a shimmering label while a step runs, settling to a done
 * label with an elapsed time. `steps` lists the trace shown underneath, collapsible once done. */
export function ThoughtLine({
  label = 'Searching sources…',
  doneLabel = 'Done',
  steps = [],
  working = true,
  elapsed,
  showTimer = true,
  collapsible = true,
  onSettle,
  className = '',
}: ThoughtLineProps) {
  const reduceMotion = useReducedMotion()
  const hasSteps = steps.length > 0

  // Internal ticking clock, only used when the caller doesn't pass a fixed `elapsed`. Freezes at
  // its last value once `working` goes false, because the interval is cleared.
  const [tickSeconds, setTickSeconds] = useState(0)
  useEffect(() => {
    if (elapsed != null || !working) return undefined
    const startedAt = performance.now()
    const id = window.setInterval(() => setTickSeconds((performance.now() - startedAt) / 1000), 100)
    return () => window.clearInterval(id)
  }, [working, elapsed])
  const seconds = elapsed ?? tickSeconds

  // Auto-collapses the trace when work settles; expanded again if it restarts. A manual toggle
  // (below) can still override this until the next transition. Derived during render, not an
  // effect, per React's "adjusting state when a prop changes" pattern.
  const [open, setOpen] = useState(true)
  const [prevWorking, setPrevWorking] = useState(working)
  if (working !== prevWorking) {
    setPrevWorking(working)
    setOpen(working || !collapsible || !hasSteps)
  }

  const settledRef = useRef(false)
  useEffect(() => {
    if (working) {
      settledRef.current = false
      return
    }
    if (settledRef.current) return
    settledRef.current = true
    onSettle?.(seconds)
  }, [working, seconds, onSettle])

  const doneText = showTimer ? `${doneLabel} in ${formatSeconds(seconds)}` : doneLabel
  const toggle = collapsible && hasSteps

  return (
    <div className={`flex flex-col items-start gap-1 font-sans text-small text-ink ${className}`}>
      <button
        type="button"
        disabled={!toggle}
        onClick={() => toggle && setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 disabled:cursor-default"
      >
        {working ? (
          <m.span
            animate={reduceMotion ? undefined : { opacity: [0.55, 1, 0.55] }}
            transition={reduceMotion ? undefined : { duration: 1.6, repeat: Infinity, ease: 'easeInOut' }}
            className="text-ink"
          >
            {label}
          </m.span>
        ) : (
          <span className="text-ink-2">{doneText}</span>
        )}
        {toggle && (
          <ChevronIcon className={`text-ink-3 transition-transform duration-300 ease-soft ${open ? 'rotate-90' : ''}`} />
        )}
        <span className="sr-only" role="status">
          {working ? label : doneText}
        </span>
      </button>

      {hasSteps && (
        <div
          style={{ transitionTimingFunction: `cubic-bezier(${EASE_SOFT.join(',')})` }}
          className={`grid overflow-hidden pl-4 transition-[grid-template-rows] duration-500 ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
        >
          <div className="flex min-h-0 flex-col gap-1.5 overflow-hidden pt-1">
            {steps.map((step, i) => {
              const done = !working || i < steps.length - 1
              return (
                <div key={`${i}-${step}`} className="flex items-center gap-2 text-micro text-ink-3">
                  {done ? (
                    <CheckIcon className="shrink-0" />
                  ) : (
                    <span aria-hidden className="size-1.5 shrink-0 animate-pulse rounded-full bg-ink" />
                  )}
                  <span className={done ? '' : 'text-ink'}>{step}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
