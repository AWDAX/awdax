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
  tourId?: string
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
const LANDING_POPOVER_WIDTH = 295
const MARGIN = 16
const GAP = 14

export function TourPopover({
  step,
  stepIndex,
  totalSteps,
  allSteps,
  rect,
  settled = true,
  tourId,
  onNext,
  onPrev,
  onSkip,
  onGoToStep,
}: Props) {
  const isLanding = tourId === 'landing-tour'
  const popoverRef = useRef<HTMLDivElement>(null)
  const [coords, setCoords] = useState<Coords>({ top: 100, left: 100 })
  const [entered, setEntered] = useState(false)

  // Trigger smooth entrance animation on mount
  useEffect(() => {
    const anim = requestAnimationFrame(() => {
      setEntered(true)
    })
    return () => cancelAnimationFrame(anim)
  }, [])

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

  const isCompact = isLanding || Boolean(step.compact)

  const computePosition = useCallback(() => {
    const vw = window.innerWidth
    const vh = window.innerHeight
    const popoverWidth = step.cardWidth ?? (isCompact ? LANDING_POPOVER_WIDTH : POPOVER_WIDTH)
    const cardWidth = Math.min(popoverWidth, vw - MARGIN * 2)
    const cardHeight = popoverRef.current?.offsetHeight ?? (isCompact ? 175 : 250)

    if (!rect) {
      // Fallback: Center screen
      setCoords({
        top: Math.max(MARGIN, (vh - cardHeight) / 2),
        left: Math.max(MARGIN, (vw - cardWidth) / 2),
      })
      return
    }

    // Landing-tour: strict position overrides and manual offsets if provided.
    if (isLanding) {
      const navH = 80 + MARGIN
      const currentCardWidth = step.cardWidth ?? LANDING_POPOVER_WIDTH
      const cornerMap: Record<string, { top: number; left: number }> = {
        'top-right': { top: navH, left: vw - currentCardWidth - MARGIN },
        'bottom-right': { top: vh - cardHeight - MARGIN, left: vw - currentCardWidth - MARGIN },
        'top-left': { top: navH, left: MARGIN },
        'bottom-left': { top: vh - cardHeight - MARGIN, left: MARGIN },
        'inside-bottom-right': {
          top: Math.min(vh - cardHeight - MARGIN, (rect?.bottom ?? vh) - cardHeight - MARGIN * 1.5),
          left: (rect?.right ?? vw) - currentCardWidth - MARGIN * 1.5,
        },
        'inside-top-right': {
          top: Math.max(navH, (rect?.top ?? 0) + MARGIN * 1.5),
          left: (rect?.right ?? vw) - currentCardWidth - MARGIN * 1.5,
        },
        'inside-top-center': {
          top: Math.max(navH, (rect?.top ?? 0) + MARGIN * 1.5),
          left: rect ? rect.left + (rect.width - currentCardWidth) / 2 : (vw - currentCardWidth) / 2,
        },
        'inside-center': {
          top: Math.max(navH, rect ? rect.top + (rect.height - cardHeight) / 2 : (vh - cardHeight) / 2),
          left: rect ? rect.left + (rect.width - currentCardWidth) / 2 : (vw - currentCardWidth) / 2,
        },
        'inside-right-center': {
          top: Math.max(navH, rect ? rect.top + (rect.height - cardHeight) / 2 : (vh - cardHeight) / 2),
          left: (rect?.right ?? vw) - currentCardWidth - MARGIN * 1.5,
        },
        'right-center': {
          top: Math.max(MARGIN, (vh - cardHeight) / 2),
          left: vw - currentCardWidth - MARGIN,
        },
        'bottom-center': {
          top: vh - cardHeight - MARGIN,
          left: Math.max(MARGIN, (vw - currentCardWidth) / 2),
        },
      }

      let chosen = cornerMap['top-right']

      if (step.landingCardPosition) {
        // Strict explicit override (no overlap checks, respects user intent exactly)
        chosen = cornerMap[step.landingCardPosition] ?? chosen
      } else {
        // Option A Auto-fallback: try corners in order until one clears the spotlight
        const defaultOrder = ['top-right', 'bottom-right', 'top-left', 'bottom-left']
        const overlaps = (t: number, l: number) =>
          t < (rect?.bottom ?? 0) &&
          t + cardHeight > (rect?.top ?? 0) &&
          l < (rect?.right ?? 0) &&
          l + currentCardWidth > (rect?.left ?? 0)

        chosen = defaultOrder.map((k) => cornerMap[k]).find((c) => !overlaps(c.top, c.left)) ?? cornerMap['top-right']
      }

      // Apply any manual nudges
      if (step.landingCardOffset) {
        chosen = {
          top: chosen.top + (step.landingCardOffset.y ?? 0),
          left: chosen.left + (step.landingCardOffset.x ?? 0),
        }
      }

      setCoords({
        top: Math.max(MARGIN, chosen.top),
        left: Math.max(MARGIN, chosen.left),
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

    // Zero-overlap protection: ensure popover sits in the dimmed area rather than covering the illuminated target
    const overlapsSpotlight =
      top < rect.bottom &&
      top + cardHeight > rect.top &&
      left < rect.right &&
      left + cardWidth > rect.left

    if (overlapsSpotlight) {
      if (spaceAbove >= cardHeight) {
        top = Math.max(MARGIN, rect.top - cardHeight - GAP)
      } else if (spaceBelow >= cardHeight) {
        top = Math.min(vh - cardHeight - MARGIN, rect.bottom + GAP)
      } else if (spaceRight >= cardWidth) {
        left = Math.min(vw - cardWidth - MARGIN, rect.right + GAP)
        top = Math.max(MARGIN, Math.min(vh - cardHeight - MARGIN, rect.top))
      } else if (spaceLeft >= cardWidth) {
        left = Math.max(MARGIN, rect.left - cardWidth - GAP)
        top = Math.max(MARGIN, Math.min(vh - cardHeight - MARGIN, rect.top))
      } else if (spaceAbove >= spaceBelow) {
        // Push as far up as possible into the dimmed area above
        top = MARGIN
      } else {
        // Push as far down as possible into the dimmed area below
        top = Math.min(vh - cardHeight - MARGIN, rect.bottom + GAP)
      }
    }

    setCoords({ top, left })
  }, [rect, step, isLanding])

  useLayoutEffect(() => {
    computePosition()
  }, [computePosition, stepIndex])

  useEffect(() => {
    window.addEventListener('resize', computePosition)
    return () => window.removeEventListener('resize', computePosition)
  }, [computePosition])

  const isLast = stepIndex === totalSteps - 1
  const isVisible = settled && entered

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
        width: `min(${step.cardWidth ?? (isCompact ? LANDING_POPOVER_WIDTH : POPOVER_WIDTH)}px, calc(100vw - 32px))`,
        zIndex: 70,
      }}
      className={`flex flex-col ${
        isCompact ? 'gap-2 p-3 shadow-[2.5px_2.5px_0px_var(--color-ink)]' : 'gap-3 p-4 shadow-[4px_4px_0px_var(--color-ink)]'
      } rounded-panel border-2 border-ink bg-canvas text-ink transition-[opacity,transform,translate] duration-400 ease-soft ${
        isVisible
          ? 'scale-100 opacity-100 translate-y-0 pointer-events-auto'
          : 'scale-[0.98] opacity-0 -translate-y-6 pointer-events-none'
      }`}
    >
      {/* Header with step counter, badge, and close button */}
      <div className={`flex items-center justify-between gap-2 border-b-2 border-line ${isCompact ? 'pb-1.5' : 'pb-2.5'}`}>
        <div className="flex flex-wrap items-center gap-1.5">
          <span
            className={`rounded-control bg-signal font-mono font-extrabold text-on-signal ${
              isCompact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-micro'
            }`}
          >
            {getStepLabel(stepIndex, step)}
          </span>
          {step.badge && (
            <span
              className={`rounded-control border border-line-strong font-mono text-ink-3 ${
                isCompact ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-micro'
              }`}
            >
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
          <span className={`grid place-items-center rounded-control hover:bg-sunken ${isCompact ? 'size-6' : 'size-7'}`}>
            <CloseIcon className={isCompact ? 'size-3.5' : 'size-4'} />
          </span>
        </button>
      </div>

      {/* Main content body */}
      <div className={`flex flex-col ${isCompact ? 'gap-1.5' : 'gap-2'}`}>
        <h2 id="tour-step-title" className={`font-display font-wide font-extrabold text-ink leading-snug ${isCompact ? 'text-body' : 'text-h3'}`}>
          {step.title}
        </h2>
        <p className={`text-ink-2 ${isCompact ? 'text-[11.5px] leading-relaxed' : 'text-small leading-relaxed'}`}>{step.content}</p>

        {step.tip && (
          <div
            className={`flex items-start rounded-control border border-signal-soft bg-signal-soft/40 text-ink ${
              isCompact ? 'mt-0.5 p-1.5 gap-1.5 text-[10px]' : 'mt-1 p-2.5 gap-2 text-micro'
            }`}
          >
            <SparkleIcon className={`shrink-0 text-ink ${isCompact ? 'size-3.5 mt-0.5' : 'size-4'}`} />
            <div className="flex-1 leading-normal">
              <strong className="font-semibold">Tip:</strong> {step.tip}
            </div>
          </div>
        )}
      </div>

      {/* Footer navigation */}
      <div className={`flex items-center justify-between gap-2 border-t-2 border-line ${isCompact ? 'pt-2' : 'pt-3'}`}>
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
              className={`rounded-full transition-all duration-300 ease-soft ${
                isCompact
                  ? i === stepIndex
                    ? 'w-3.5 h-1.5 bg-ink'
                    : 'size-1.5 bg-line-strong hover:bg-ink-3'
                  : i === stepIndex
                  ? 'w-5 size-2 bg-ink'
                  : 'size-2 bg-line-strong hover:bg-ink-3'
              }`}
            />
          ))}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1.5">
          {stepIndex > 0 && (
            <button
              type="button"
              onClick={onPrev}
              tabIndex={-1}
              className={buttonClass('secondary', 'md', `${isCompact ? 'h-7 px-2 text-[11px]' : 'h-8 px-2.5 text-small'} focus:outline-none focus-visible:outline-none`)}
            >
              Back
            </button>
          )}

          <button
            type="button"
            onClick={onNext}
            tabIndex={-1}
            className={buttonClass('primary', 'md', `${isCompact ? 'h-7 px-2.5 text-[11px]' : 'h-8 px-3 text-small'} focus:outline-none focus-visible:outline-none`)}
          >
            {isLast ? (
              'Got it'
            ) : (
              <span className="flex items-center gap-1">
                Next <ArrowIcon className={isCompact ? 'size-3' : 'size-3.5'} />
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Dedicated Keyboard shortcut hints footer */}
      <div className={`flex items-center justify-center gap-1.5 border-t border-line/60 text-ink-3 select-none ${isCompact ? 'pt-1.5 text-[9.5px]' : 'pt-2 text-micro'}`}>
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[9px] text-ink-2">←</kbd>
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[9px] text-ink-2">→</kbd>
        <span>navigate</span>
        <span className="px-1 text-line-strong">|</span>
        <kbd className="rounded border border-line-strong bg-sunken px-1.5 py-0.5 font-mono text-[9px] text-ink-2">Esc</kbd>
        <span>to skip</span>
      </div>
    </aside>
  )
}
