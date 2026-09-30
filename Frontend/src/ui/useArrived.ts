import { useEffect, useState } from 'react'

/**
 * False on the first paint, true two frames later. A transition keyed on it plays on mount,
 * because the browser has painted the "before" state first.
 */
export function useArrived() {
  const [arrived, setArrived] = useState(false)
  useEffect(() => {
    let second = 0
    const first = requestAnimationFrame(() => {
      second = requestAnimationFrame(() => setArrived(true))
    })
    return () => {
      cancelAnimationFrame(first)
      cancelAnimationFrame(second)
    }
  }, [])
  return arrived
}
