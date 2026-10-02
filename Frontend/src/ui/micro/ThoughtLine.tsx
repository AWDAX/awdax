import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { animate, useReducedMotion } from 'motion/react'
import { ChevronIcon, SparkleIcon } from '../appIcons.tsx'
import { CheckIcon } from '../icons.tsx'
import { EASE_DRAW, EASE_SOFT } from '../motion.ts'
import './ThoughtLine.css'

export type ThoughtLineProps = {
  /** The working line. It shimmers, and it is the spoken text. */
  label?: string
  /** The settled line; the frozen time follows it when `showTimer` is on. */
  doneLabel?: string
  glyph?: 'sparkle' | 'dot' | 'none' | ReactNode
  /** The trace beneath the line. The last step is current while working; earlier ones tick. */
  steps?: string[]
  /** The line toggles the trace, with a chevron. */
  collapsible?: boolean
  collapseOnSettle?: boolean
  fontSize?: number
  breathPeriod?: number
  breathDepth?: number
  shimmer?: boolean
  shimmerDuration?: number
  settleDuration?: number
  settleBlur?: number
  working?: boolean
  /** Controlled seconds: the internal clock never runs. */
  elapsed?: number
  /** Wall-clock start (epoch ms) for the internal clock, so a page opened mid-run shows the real time. */
  startedAt?: number
  showTimer?: boolean
  onSettle?: (seconds: number) => void
  className?: string
  style?: CSSProperties
}

const GLYPH_DONE = 0.55
const EMPTY: string[] = []

const fmt = (ds: number) => (ds < 600 ? `${(ds / 10).toFixed(1)}s` : `${Math.floor(ds / 600)}m ${((ds % 600) / 10).toFixed(1)}s`)
const spoken = (ds: number) =>
  ds < 600 ? `${(ds / 10).toFixed(1)} seconds` : `${Math.floor(ds / 600)} minutes ${((ds % 600) / 10).toFixed(1)} seconds`

/**
 * The "working" line of an agent: a breathing sparkle and a shimmering label with a live clock, settling into a
 * sentence with the frozen time ("Finished in 3.5s"), and a trace of steps beneath it (ticked, the current one
 * pulsing) that folds away when it settles. React Bits' ThoughtLine; see CREDITS.md for what changed.
 */
export function ThoughtLine({
  label = 'Thinking…',
  doneLabel = 'Done',
  glyph = 'sparkle',
  steps = EMPTY,
  collapsible = true,
  collapseOnSettle = true,
  fontSize = 16,
  breathPeriod = 1.6,
  breathDepth = 0.45,
  shimmer = true,
  shimmerDuration = 1.8,
  settleDuration = 350,
  settleBlur = 2,
  working = true,
  elapsed,
  startedAt,
  showTimer = true,
  onSettle,
  className = '',
  style,
}: ThoughtLineProps) {
  const reduce = useReducedMotion() ?? false
  const hasTrace = steps.length > 0
  const depth = reduce ? Math.min(breathDepth, 0.2) : breathDepth
  const period = reduce ? breathPeriod * 1.5 : breathPeriod
  const trough = 1 - depth
  const sheen = shimmer && !reduce

  const glyphRef = useRef<HTMLSpanElement>(null)
  const breathRef = useRef<HTMLSpanElement>(null)
  const timerRef = useRef<HTMLSpanElement>(null)
  const stackRef = useRef<HTMLSpanElement>(null)
  const workRef = useRef<HTMLSpanElement>(null)
  const doneRef = useRef<HTMLSpanElement>(null)
  const prevWorking = useRef(working)

  // Open while working, folded once it settles (unless told not to). Adjusted during render, not in an effect.
  const [open, setOpen] = useState(true)
  const [seen, setSeen] = useState(working)
  if (working !== seen) {
    setSeen(working)
    if (working) setOpen(true)
    else if (collapseOnSettle) setOpen(false)
  }

  // The clock, in tenths: from `startedAt` (or the moment work began) while working, frozen once it settles. A
  // hidden timer doesn't tick (no re-render ten times a second for nothing).
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (elapsed != null || !working || !showTimer) return undefined
    const origin = startedAt ?? Date.now()
    const paint = () => setTick(Math.max(0, Math.floor((Date.now() - origin) / 100)))
    const first = window.setTimeout(paint, 0)
    const id = window.setInterval(paint, 100)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(id)
    }
  }, [working, elapsed, startedAt, showTimer])
  const ds = elapsed != null ? Math.round(elapsed * 10) : tick

  // The breath: the glyph (and the label, when it doesn't shimmer) dims and returns; settling dims the glyph.
  useEffect(() => {
    const glyphEl = glyphRef.current
    const breathEl = breathRef.current
    if (!breathEl) return undefined
    const loop = (el: HTMLElement, delay: number) =>
      animate(el, { opacity: [trough, 1, trough] }, { duration: period, ease: EASE_DRAW, repeat: Infinity, delay })
    let cancelled = false
    const running: ReturnType<typeof animate>[] = []
    if (working && depth > 0) {
      if (sheen) running.push(animate(breathEl, { opacity: 1 }, { duration: 0.2, ease: EASE_SOFT }))
      if (glyphEl) {
        const lead = animate(glyphEl, { opacity: trough }, { duration: 0.2, ease: EASE_SOFT })
        running.push(lead)
        void lead.then(() => {
          if (cancelled) return
          running.push(loop(glyphEl, 0))
          if (!sheen) running.push(loop(breathEl, 0.14))
        })
      } else if (!sheen) running.push(loop(breathEl, 0.14))
    } else {
      const s = working ? 0.2 : settleDuration / 1000
      if (glyphEl) running.push(animate(glyphEl, { opacity: working ? 1 : GLYPH_DONE }, { duration: s, ease: EASE_SOFT }))
      running.push(animate(breathEl, { opacity: 1 }, { duration: s, ease: EASE_SOFT }))
    }
    return () => {
      cancelled = true
      running.forEach((a) => a.stop())
    }
  }, [working, period, depth, trough, settleDuration, glyph, sheen])

  // The timer sits after whichever label is showing, and glides across when the line settles.
  useLayoutEffect(() => {
    const t = timerRef.current
    const stack = stackRef.current
    if (!t || !stack) return undefined
    const place = (glide: boolean) => {
      const active = working ? workRef.current : doneRef.current
      if (!active) return
      if (!glide) t.style.transition = 'none'
      t.style.transform = `translateX(${active.offsetWidth - stack.offsetWidth}px)`
      if (!glide) {
        void t.offsetWidth
        t.style.transition = ''
      }
    }
    place(prevWorking.current !== working)
    prevWorking.current = working
    const ro = new ResizeObserver(() => place(false))
    if (workRef.current) ro.observe(workRef.current)
    if (doneRef.current) ro.observe(doneRef.current)
    return () => ro.disconnect()
  }, [working, label, doneLabel, fontSize, showTimer])

  const latestDs = useRef(ds)
  const latestSettle = useRef(onSettle)
  useEffect(() => {
    latestDs.current = ds
    latestSettle.current = onSettle
  })
  useEffect(() => {
    if (!working) latestSettle.current?.(latestDs.current / 10)
  }, [working])

  const toggle = hasTrace && collapsible
  const announce = working ? label : showTimer ? `${doneLabel} ${spoken(ds)}` : doneLabel
  const head = (
    <>
      {glyph !== 'none' && (
        <span ref={glyphRef} className="thought-line__glyph" aria-hidden="true">
          {glyph === 'sparkle' ? <SparkleIcon /> : glyph === 'dot' ? <span className="thought-line__dot" /> : glyph}
        </span>
      )}
      <span ref={stackRef} className="thought-line__label" aria-hidden="true">
        <span ref={workRef} className="thought-line__text" data-active={working ? '' : undefined}>
          <span ref={breathRef} className="thought-line__breath" data-shimmer={sheen ? '' : undefined}>
            {label}
          </span>
        </span>
        <span ref={doneRef} className="thought-line__text thought-line__text--done" data-active={working ? undefined : ''}>
          {doneLabel}
        </span>
      </span>
      {showTimer && (
        <span ref={timerRef} className="thought-line__timer" data-done={working ? undefined : ''} aria-hidden="true">
          {fmt(ds)}
        </span>
      )}
      {collapsible && (
        <span className="thought-line__chevron" data-on={hasTrace ? '' : undefined} aria-hidden="true">
          <ChevronIcon width="1em" height="1em" />
        </span>
      )}
      <span className="sr-only" role="status">
        {announce}
      </span>
    </>
  )

  const vars = {
    '--tl-font': `${fontSize}px`,
    '--tl-settle': `${settleDuration}ms`,
    '--tl-blur': `${settleBlur}px`,
    '--tl-shimmer': `${shimmerDuration}s`,
  } as CSSProperties

  return (
    <div
      className={`thought-line${className ? ` ${className}` : ''}`}
      data-working={working ? '' : undefined}
      data-open={open && hasTrace ? '' : undefined}
      style={{ ...vars, ...style }}
    >
      {collapsible ? (
        <button
          type="button"
          className="thought-line__head"
          data-toggle={toggle ? '' : undefined}
          aria-expanded={toggle ? open : undefined}
          tabIndex={toggle ? 0 : -1}
          onClick={() => toggle && setOpen((v) => !v)}
        >
          {head}
        </button>
      ) : (
        <div className="thought-line__head">{head}</div>
      )}
      {hasTrace && (
        <div className="thought-line__trace" data-open={open ? '' : undefined} aria-hidden={!open}>
          <div className="thought-line__fold">
            <div className="thought-line__steps">
              {steps.map((text, i) => {
                const done = !working || i < steps.length - 1
                return (
                  <div key={`${i}-${text}`} className="thought-line__step" data-done={done ? '' : undefined}>
                    <span className="thought-line__mark" aria-hidden="true">
                      {done ? <CheckIcon width="1em" height="1em" /> : <i className="thought-line__pulse" />}
                    </span>
                    <span className="thought-line__step-text" title={text}>
                      {text}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
