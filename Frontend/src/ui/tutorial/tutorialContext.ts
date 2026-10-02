import { createContext, useContext } from 'react'

export type TutorialContextValue = {
  openTutorial: () => void
}

export const TutorialContext = createContext<TutorialContextValue | null>(null)

/** `openTutorial()` shows the tutorial video. Must be used under `<TutorialProvider>`. */
export function useTutorial() {
  const ctx = useContext(TutorialContext)
  if (!ctx) throw new Error('useTutorial must be used within a TutorialProvider')
  return ctx
}
