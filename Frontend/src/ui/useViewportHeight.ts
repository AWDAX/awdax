import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('resize', onChange)
  return () => window.removeEventListener('resize', onChange)
}

/** The window's inner height in px, kept current on resize (and on entering or leaving full screen). */
export function useViewportHeight(): number {
  return useSyncExternalStore(subscribe, () => window.innerHeight, () => 800)
}
