import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../../app/auth/authContext.ts'
import { TutorialContext } from './tutorialContext.ts'
import { TutorialDialog } from './TutorialDialog.tsx'
import { hasSeenTutorial, markTutorialSeen } from './tutorialSeen.ts'
import { TUTORIAL_SRC } from './tutorialSource.ts'

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
  // A first visit that should see the video, waiting for it to load.
  const [firstVisit, setFirstVisit] = useState(false)
  // The user id the first-visit check already ran for, so route changes and re-renders never reopen it.
  const [checkedFor, setCheckedFor] = useState<string | null | undefined>(undefined)

  // Adjusting state during render (not in an effect) avoids a second render pass for the one-time check.
  if (!loading && checkedFor !== userId) {
    setCheckedFor(userId)
    setFirstVisit(!hasSeenTutorial(getStorage(), userId))
  }

  // Open on its own only once the video can actually play: without the file, a first visit met a dialog saying
  // the video isn't available. Not marked seen in that case, so it still shows once the video is added.
  useEffect(() => {
    if (!firstVisit) return undefined
    const probe = document.createElement('video')
    probe.preload = 'metadata'
    probe.onloadedmetadata = () => setOpen(true)
    probe.src = TUTORIAL_SRC
    return () => {
      probe.onloadedmetadata = null
      probe.removeAttribute('src')
      probe.load()
    }
  }, [firstVisit])

  const openTutorial = useCallback(() => setOpen(true), [])
  const close = useCallback(() => {
    setOpen(false)
    setFirstVisit(false)
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
