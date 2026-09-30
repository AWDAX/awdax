import { useCallback, useEffect, useRef, useState } from 'react'
import { useReducedMotion } from 'motion/react'

/**
 * A pausable clock from 0 to `end` ms. Each animation frame it asks `at(t)` for a frame and
 * re-renders only when `same` says the frame changed. With reduced motion it starts at the end
 * and never plays by itself.
 */
export function useTimeline<F>(end: number, at: (t: number) => F, same: (a: F, b: F) => boolean, active: boolean) {
  const reduced = useReducedMotion() ?? false
  const t = useRef(reduced ? end : 0)
  const [frame, setFrame] = useState(() => at(reduced ? end : 0))
  const [playing, setPlaying] = useState(!reduced)
  const [finished, setFinished] = useState(reduced)

  useEffect(() => {
    if (!playing || !active) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      // Clamp the step so a tab coming back from the background doesn't skip the run.
      t.current = Math.min(end, t.current + Math.min(100, now - last))
      last = now
      const next = at(t.current)
      setFrame((prev) => (same(prev, next) ? prev : next))
      if (t.current >= end) {
        setPlaying(false)
        setFinished(true)
        return
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, active, end, at, same])

  const pause = useCallback(() => setPlaying(false), [])

  const play = useCallback(() => {
    // Reduced motion never runs the clock, even on an explicit replay: the final frame is the run.
    if (reduced) return
    if (t.current >= end) {
      t.current = 0
      setFrame(at(0))
      setFinished(false)
    }
    setPlaying(true)
  }, [end, at, reduced])

  return { frame, playing, finished, pause, play }
}
