import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../../app/auth/authContext.ts'
import { TutorialContext } from './tutorialContext.ts'
import { TutorialDialog } from './TutorialDialog.tsx'
import { hasSeenTutorial, markTutorialSeen } from './tutorialSeen.ts'

// Reading `localStorage` itself can throw when site data is blocked.
function getStorage(): Storage | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

/** Shows the tutorial video once, the first time a user opens the app, and again whenever a button asks. */
export function TutorialProvider({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const userId = user?.id ?? null
  const [open, setOpen] = useState(false)
  // The user id the first-visit check already ran for, so route changes and re-renders never reopen it.
  const [checkedFor, setCheckedFor] = useState<string | null | undefined>(undefined)

  // Adjusting state during render (not in an effect) avoids a second render pass for the one-time check.
  if (!loading && checkedFor !== userId) {
    setCheckedFor(userId)
    if (!hasSeenTutorial(getStorage(), userId)) setOpen(true)
  }

  const openTutorial = useCallback(() => setOpen(true), [])
  const close = useCallback(() => {
    setOpen(false)
    markTutorialSeen(getStorage(), userId)
  }, [userId])
  const value = useMemo(() => ({ openTutorial }), [openTutorial])

  return (
    <TutorialContext.Provider value={value}>
      {children}
      {open && <TutorialDialog onClose={close} />}
    </TutorialContext.Provider>
  )
}
