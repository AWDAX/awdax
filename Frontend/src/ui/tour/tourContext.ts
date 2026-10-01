import { createContext, useContext } from 'react'
import type { TourDefinition, TourStep } from './tourTypes.ts'

export type TourContextValue = {
  activeTour: TourDefinition | null
  currentStepIndex: number
  currentStep: TourStep | null
  isActive: boolean
  startTour: (tourId: string, startIndex?: number) => void
  nextStep: () => void
  prevStep: () => void
  goToStep: (index: number) => void
  endTour: () => void
  hasSeenTour: (tourId: string) => boolean
  markTourSeen: (tourId: string) => void
  resetSeenTours: () => void
}

export const TourContext = createContext<TourContextValue | null>(null)

export function useTour(): TourContextValue {
  const ctx = useContext(TourContext)
  if (!ctx) {
    throw new Error('useTour must be used within a TourProvider')
  }
  return ctx
}
