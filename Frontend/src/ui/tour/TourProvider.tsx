import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { TourContext, type TourContextValue } from './tourContext.ts'
import { TOURS } from './tourRegistry.ts'
import type { TourDefinition } from './tourTypes.ts'
import { TourHost } from './TourHost.tsx'

const SEEN_PREFIX = 'awdax.tour.seen.'

function isSeen(tourId: string): boolean {
  try {
    return localStorage.getItem(`${SEEN_PREFIX}${tourId}`) === 'true'
  } catch {
    return false
  }
}

function setSeen(tourId: string): void {
  try {
    localStorage.setItem(`${SEEN_PREFIX}${tourId}`, 'true')
  } catch {
    // ignore storage restrictions
  }
}

export function TourProvider({ children }: { children: ReactNode }) {
  const [activeTour, setActiveTour] = useState<TourDefinition | null>(null)
  const [currentStepIndex, setCurrentStepIndex] = useState(0)

  const startTour = useCallback((tourId: string, startIndex = 0) => {
    const tour = TOURS[tourId]
    if (!tour || tour.steps.length === 0) return
    setActiveTour(tour)
    setCurrentStepIndex(Math.max(0, Math.min(startIndex, tour.steps.length - 1)))
  }, [])

  const endTour = useCallback(() => {
    if (activeTour) {
      setSeen(activeTour.id)
    }
    setActiveTour(null)
    setCurrentStepIndex(0)
  }, [activeTour])

  const nextStep = useCallback(() => {
    if (!activeTour) return
    if (currentStepIndex < activeTour.steps.length - 1) {
      setCurrentStepIndex((prev) => prev + 1)
    } else {
      endTour()
    }
  }, [activeTour, currentStepIndex, endTour])

  const prevStep = useCallback(() => {
    if (!activeTour) return
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1)
    }
  }, [activeTour, currentStepIndex])

  const goToStep = useCallback(
    (index: number) => {
      if (!activeTour) return
      if (index >= 0 && index < activeTour.steps.length) {
        setCurrentStepIndex(index)
      }
    },
    [activeTour],
  )

  const hasSeenTour = useCallback((tourId: string) => isSeen(tourId), [])
  const markTourSeen = useCallback((tourId: string) => setSeen(tourId), [])
  const resetSeenTours = useCallback(() => {
    try {
      for (const key of Object.keys(TOURS)) {
        localStorage.removeItem(`${SEEN_PREFIX}${key}`)
      }
    } catch {
      // ignore
    }
  }, [])

  const currentStep = useMemo(() => {
    if (!activeTour || !activeTour.steps[currentStepIndex]) return null
    return activeTour.steps[currentStepIndex]
  }, [activeTour, currentStepIndex])

  const value = useMemo<TourContextValue>(
    () => ({
      activeTour,
      currentStepIndex,
      currentStep,
      isActive: Boolean(activeTour && currentStep),
      startTour,
      nextStep,
      prevStep,
      goToStep,
      endTour,
      hasSeenTour,
      markTourSeen,
      resetSeenTours,
    }),
    [activeTour, currentStepIndex, currentStep, startTour, nextStep, prevStep, goToStep, endTour, hasSeenTour, markTourSeen, resetSeenTours],
  )

  return (
    <TourContext.Provider value={value}>
      {children}
      <TourHost />
    </TourContext.Provider>
  )
}
