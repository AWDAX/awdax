import { useLayoutEffect, useRef, useState } from 'react'

/** The element's content width, kept current as it resizes. 0 until measured. */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // ResizeObserver reports once on observe, so the first width arrives without a manual read.
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return [ref, width] as const
}
