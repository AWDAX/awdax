import { useEffect } from 'react'
import { useTour } from './tourContext.ts'

/**
 * Automatically starts a tour when the component mounts if the user has not seen it yet.
 * @param tourId The ID of the tour in the registry.
 * @param delayMs Optional delay in milliseconds before triggering (default 800ms).
 * @param enabled Whether auto-triggering is enabled (default true).
 */
export function useAutoTour(tourId: string, delayMs = 800, enabled = false) {
  const { startTour, hasSeenTour, isActive } = useTour()

  useEffect(() => {
    if (!enabled || isActive || hasSeenTour(tourId)) return

    const timer = setTimeout(() => {
      startTour(tourId)
    }, delayMs)

    return () => clearTimeout(timer)
  }, [tourId, delayMs, enabled, startTour, hasSeenTour, isActive])
}
