import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ArrowIcon } from '../icons.tsx'
import { CloseIcon, SparkleIcon } from '../appIcons.tsx'
import { buttonClass } from '../buttonClass.ts'
import type { TargetRect, TourStep } from './tourTypes.ts'

type Props = {
  step: TourStep
  stepIndex: number
  totalSteps: number
  allSteps?: TourStep[]
  rect: TargetRect | null
  settled?: boolean
  onNext: () => void
  onPrev: () => void
  onSkip: () => void
  onGoToStep: (index: number) => void
}

type Coords = {
  top: number
  left: number
}

const POPOVER_WIDTH = 380
const MARGIN = 16
const GAP = 14

export function TourPopover({
  step,
  stepIndex,
  totalSteps,
  allSteps,
  rect,
  settled = true,
  onNext,
  onPrev,
  onSkip,
  onGoToStep,
}: Props) {
  const popoverRef = useRef<HTMLDivElement>(null)
  const [coords, setCoords] = useState<Coords>({ top: 100, left: 100 })

  const getStepLabel = useCallback(
    (idx: number, s: TourStep) => {
      if (s.stepLabel) return s.stepLabel

      if (allSteps) {
        const numberedSteps = allSteps.filter((item) => !item.stepLabel)
        const currentNumberedIdx = allSteps.slice(0, idx + 1).filter((item) => !item.stepLabel).length
        return `Step ${currentNumberedIdx} of ${numberedSteps.length}`
      }

      return `Step ${idx + 1} of ${totalSteps}`
    },
    [allSteps, totalSteps],
  )

  const computePosition = useCallback(() => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const cardWidth = Math.min(POPOVER_WIDTH, vw - MARGIN * 2)
    const cardHeight = popoverRef.current?.offsetHeight ?? 250

    if (!rect) {
      // Fallback: Center screen
      setCoords({
        top: Math.max(MARGIN, (vh - cardHeight) / 2),
        left: Math.max(MARGIN, (vw - cardWidth) / 2),
      })
      return
    }

    const pref = step.placement ?? 'auto'

    // Compute available clearances around the target element
    const spaceBelow = vh - (rect.bottom + GAP) - MARGIN
    const spaceAbove = rect.top - GAP - MARGIN
    const spaceRight = vw - (rect.right + GAP) - MARGIN
    const spaceLeft = rect.left - GAP - MARGIN

    const fitsBelow = spaceBelow >= cardHeight
    const fitsAbove = spaceAbove >= cardHeight
    const fitsRight = spaceRight >= cardWidth
    const fitsLeft = spaceLeft >= cardWidth

    let chosenSide: 'top' | 'bottom' | 'left' | 'right'

    if (pref === 'center') {
      setCoords({
        top: Math.max(MARGIN, (vh - cardHeight) / 2),
        left: Math.max(MARGIN, (vw - cardWidth) / 2),
      })
      return
    }

    // Determine optimal placement side that guarantees ZERO overlap with highlighted target
    if (pref === 'bottom') {
      if (fitsBelow) chosenSide = 'bottom'
      else if (fitsAbove) chosenSide = 'top'
      else if (fitsRight) chosenSide = 'right'
      else if (fitsLeft) chosenSide = 'left'
      else chosenSide = spaceBelow >= spaceAbove ? 'bottom' : 'top'
    } else if (pref === 'top') {
      if (fitsAbove) chosenSide = 'top'
      else if (fitsBelow) chosenSide = 'bottom'
      else if (fitsRight) chosenSide = 'right'
      else if (fitsLeft) chosenSide = 'left'
      else chosenSide = spaceAbove >= spaceBelow ? 'top' : 'bottom'
    } else if (pref === 'right') {
      if (fitsRight) chosenSide = 'right'
      else if (fitsLeft) chosenSide = 'left'
      else if (fitsBelow) chosenSide = 'bottom'
      else if (fitsAbove) chosenSide = 'top'
      else chosenSide = 'right'
    } else if (pref === 'left') {
      if (fitsLeft) chosenSide = 'left'
      else if (fitsRight) chosenSide = 'right'
      else if (fitsBelow) chosenSide = 'bottom'
      else if (fitsAbove) chosenSide = 'top'
      else chosenSide = 'left'
    } else {
      // 'auto': prioritize bottom -> top -> right -> left
      if (fitsBelow) chosenSide = 'bottom'
      else if (fitsAbove) chosenSide = 'top'
      else if (fitsRight) chosenSide = 'right'
      else if (fitsLeft) chosenSide = 'left'
      else chosenSide = spaceBelow >= spaceAbove ? 'bottom' : 'top'
    }

    let top: number
    let left: number

    if (chosenSide === 'bottom') {
      top = rect.bottom + GAP
      // Horizontally center with target or clamp within viewport margins
      left = Math.max(MARGIN, Math.min(vw - cardWidth - MARGIN, rect.left + (rect.width - cardWidth) / 2))
      // Double check boundary collision
      if (top + cardHeight > vh - MARGIN && spaceAbove > spaceBelow) {
        top = Math.max(MARGIN, rect.top - cardHeight - GAP)
      }
    } else if (chosenSide === 'top') {
      top = rect.top - cardHeight - GAP
      left = Math.max(MARGIN, Math.min(vw - cardWidth - MARGIN, rect.left + (rect.width - cardWidth) / 2))
      // Double check boundary collision
      if (top < MARGIN && spaceBelow > spaceAbove) {
        top = Math.min(vh - cardHeight - MARGIN, rect.bottom + GAP)
      }
    } else if (chosenSide === 'right') {
      left = rect.right + GAP
      top = Math.max(MARGIN, Math.min(vh - cardHeight - MARGIN, rect.top + (rect.height - cardHeight) / 2))
    } else {
      // left
      left = rect.left - cardWidth - GAP
      top = Math.max(MARGIN, Math.min(vh - cardHeight - MARGIN, rect.top + (rect.height - cardHeight) / 2))
    }

    // Strict boundary clamps
    top = Math.max(MARGIN, Math.min(vh - cardHeight - MARGIN, top))
    left = Math.max(MARGIN, Math.min(vw - cardWidth - MARGIN, left))

    setCoords({ top, left })
  }, [rect, step])

  useLayoutEffect(() => {
    computePosition()
  }, [computePosition, stepIndex])

  useEffect(() => {
    window.addEventListener('resize', computePosition)
    return () => window.removeEventListener('resize', computePosition)
  }, [computePosition])

  const isLast = stepIndex === totalSteps - 1

  return (
    <aside
      ref={popoverRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby="tour-step-title"
      style={{
        position: 'fixed',
        top: `${coords.top}px`,
        left: `${coords.left}px`,
        width: `min(${POPOVER_WIDTH}px, calc(100vw - 32px))`,
        zIndex: 70,
      }}
      className={`flex flex-col gap-3 rounded-panel border-2 border-ink bg-canvas p-4 text-ink shadow-[4px_4px_0px_var(--color-ink)] transition-all duration-500 ease-soft ${
        settled
          ? 'scale-100 opacity-100 translate-y-0 pointer-events-auto'
          : 'scale-[0.98] opacity-0 -translate-y-8 pointer-events-none'
      }`}
    >
      {/* Header with step counter, badge, and close button */}
      <div className="flex items-center justify-between gap-2 border-b-2 border-line pb-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-control bg-signal px-2 py-0.5 font-mono text-micro font-extrabold text-on-signal">
            {getStepLabel(stepIndex, step)}
          </span>
          {step.badge && (
            <span className="rounded-control border border-line-strong px-2 py-0.5 font-mono text-micro text-ink-3">
              {step.badge}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={onSkip}
          aria-label="Close tour"
          className="group flex items-center gap-1 rounded-control text-ink-3 hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
        >
          <span className="grid size-7 place-items-center rounded-control hover:bg-sunken">
            <CloseIcon />
          </span>
        </button>
      </div>

      {/* Main content body */}
      <div className="flex flex-col gap-2">
        <h2 id="tour-step-title" className="font-display font-wide text-h3 font-extrabold text-ink leading-snug">
          {step.title}
        </h2>
        <p className="text-small text-ink-2 leading-relaxed">{step.content}</p>

        {step.tip && (
          <div className="mt-1 flex items-start gap-2 rounded-control border border-signal-soft bg-signal-soft/40 p-2.5 text-micro text-ink">
            <SparkleIcon className="size-4 shrink-0 text-ink" />
            <div className="flex-1 leading-normal">
              <strong className="font-semibold">Tip:</strong> {step.tip}
            </div>
          </div>
        )}
      </div>

      {/* Footer navigation */}
      <div className="mt-1 flex items-center justify-between gap-2 border-t-2 border-line pt-3">
        {/* Step dots */}
        <div className="flex items-center gap-1" role="tablist" aria-label="Tour steps">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <button
              key={i}
              type="button"
              role="tab"
              aria-selected={i === stepIndex}
              aria-label={allSteps ? getStepLabel(i, allSteps[i]) : `Go to step ${i + 1}`}
              onClick={() => onGoToStep(i)}
              className={`size-2 rounded-full transition-all duration-300 ease-soft ${
                i === stepIndex ? 'w-5 bg-ink' : 'bg-line-strong hover:bg-ink-3'
              }`}
            />
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {stepIndex > 0 && (
            <button
              type="button"
              onClick={onPrev}
              tabIndex={-1}
              className={buttonClass('secondary', 'md', 'h-8 px-2.5 text-small focus:outline-none focus-visible:outline-none')}
            >
              Back
            </button>
          )}

          <button
            type="button"
            onClick={onNext}
            tabIndex={-1}
            className={buttonClass('primary', 'md', 'h-8 px-3 text-small focus:outline-none focus-visible:outline-none')}
          >
            {isLast ? (
              'Got it'
            ) : (
              <span className="flex items-center gap-1.5">
                Next <ArrowIcon className="size-3.5" />
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Dedicated Keyboard shortcut hints footer */}
      <div className="flex items-center justify-center gap-1.5 border-t border-line/60 pt-2 text-micro text-ink-3 select-none">
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[10px] text-ink-2">←</kbd>
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[10px] text-ink-2">→</kbd>
        <span>navigate</span>
        <span className="px-1 text-line-strong">|</span>
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[10px] text-ink-2">Esc</kbd>
        <span>to skip</span>
      </div>
    </aside>
  )
}
