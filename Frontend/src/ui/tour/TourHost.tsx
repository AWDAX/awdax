import { useCallback, useEffect, useState } from 'react'
import { useLenis } from 'lenis/react'
import { useTour } from './tourContext.ts'
import type { TargetRect } from './tourTypes.ts'
import { TourBackdrop } from './TourBackdrop.tsx'
import { TourPopover } from './TourPopover.tsx'

export function TourHost() {
  const { activeTour, currentStepIndex, currentStep, isActive, nextStep, prevStep, goToStep, endTour } = useTour()
  const lenis = useLenis()
  const [targetRect, setTargetRect] = useState<TargetRect | null>(null)
  const [settledStep, setSettledStep] = useState<number | null>(null)

  const settled = settledStep === currentStepIndex

  const updateRect = useCallback(() => {
    if (!currentStep) {
      setTargetRect(null)
      return
    }

    const el = document.querySelector(currentStep.target)
    if (el) {
      const domRect = el.getBoundingClientRect()
      setTargetRect({
        top: domRect.top,
        left: domRect.left,
        width: domRect.width,
        height: domRect.height,
        bottom: domRect.bottom,
        right: domRect.right,
      })
    } else {
      setTargetRect(null)
    }
  }, [currentStep])

  // Scroll target element into view first, syncing coordinates frame-by-frame until completely stationary
  useEffect(() => {
    if (!isActive || !currentStep) return

    let animId: number
    let isCancelled = false
    const startTime = performance.now()
    let lastY = window.scrollY
    let stationaryFrames = 0
    let hasScrolled = false

    // 1. Scroll: Bring targeted element smoothly into view (using Lenis when present to glide past pinned sections)
    const el = document.querySelector(currentStep.target) as HTMLElement | null
    if (el) {
      if (lenis) {
        const offset = -Math.max(20, Math.floor((window.innerHeight - el.offsetHeight) / 2))
        lenis.scrollTo(el, {
          offset,
          duration: 0.65,
          lock: true,
          onComplete: () => {
            if (isCancelled) return
            updateRect()
            setSettledStep(currentStepIndex)
          },
        })
      } else {
        el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
      }
    }

    // 2. Continuously sample targetRect on each animation frame until scroll velocity reaches 0
    const syncLoop = () => {
      if (isCancelled) return
      updateRect()
      const currentY = window.scrollY
      const elapsed = performance.now() - startTime

      if (Math.abs(currentY - lastY) > 0.5) {
        hasScrolled = true
        stationaryFrames = 0
      } else if (hasScrolled || elapsed > 150) {
        stationaryFrames++
      }
      lastY = currentY

      // Settle as soon as stationary for 5 frames or at safety timeout
      if ((stationaryFrames >= 5 && elapsed >= 250) || elapsed >= 800) {
        updateRect()
        setSettledStep(currentStepIndex)
        return
      }

      animId = requestAnimationFrame(syncLoop)
    }

    animId = requestAnimationFrame(syncLoop)

    return () => {
      isCancelled = true
      cancelAnimationFrame(animId)
    }
  }, [isActive, currentStep, currentStepIndex, lenis, updateRect])

  // Coordinate rect updates with Lenis scroll events
  useEffect(() => {
    if (!isActive || !lenis) return

    const onLenisScroll = () => {
      requestAnimationFrame(updateRect)
    }

    lenis.on('scroll', onLenisScroll)
    return () => {
      lenis.off('scroll', onLenisScroll)
    }
  }, [isActive, lenis, updateRect])

  // Prevent background scrolling (wheel, touch, arrow keys) while tour is active
  useEffect(() => {
    if (!isActive) return

    const preventScroll = (e: Event) => {
      e.preventDefault()
    }

    window.addEventListener('wheel', preventScroll, { passive: false })
    window.addEventListener('touchmove', preventScroll, { passive: false })

    return () => {
      window.removeEventListener('wheel', preventScroll)
      window.removeEventListener('touchmove', preventScroll)
    }
  }, [isActive])

  // Keep rect updated on resize
  useEffect(() => {
    if (!isActive) return

    const onResize = () => {
      requestAnimationFrame(updateRect)
    }

    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [isActive, updateRect])

  // Global Keyboard shortcuts & scroll suppression: Escape (Exit), ArrowRight / Enter (Next), ArrowLeft (Prev)
  useEffect(() => {
    if (!isActive) return

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const isInput = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable

      // Suppress default page scrolling keys while tour is active
      const scrollKeys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']
      if (scrollKeys.includes(e.key) && !isInput) {
        e.preventDefault()
        return
      }

      if (isInput && e.key !== 'Escape') return

      if (e.key === 'Escape') {
        e.preventDefault()
        endTour()
      } else if (e.key === 'ArrowRight' || e.key === 'Enter') {
        e.preventDefault()
        nextStep()
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        prevStep()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isActive, nextStep, prevStep, endTour])

  if (!isActive || !activeTour || !currentStep) {
    return null
  }

  return (
    <>
      <TourBackdrop
        rect={targetRect}
        settled={settled}
        padding={currentStep.highlightPadding ?? 8}
        radius={currentStep.spotlightRadius ?? 6}
      />
      <TourPopover
        step={currentStep}
        stepIndex={currentStepIndex}
        totalSteps={activeTour.steps.length}
        allSteps={activeTour.steps}
        rect={targetRect}
        settled={settled}
        onNext={nextStep}
        onPrev={prevStep}
        onSkip={endTour}
        onGoToStep={goToStep}
      />
    </>
  )
}
