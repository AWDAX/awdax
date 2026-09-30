import { useLayoutEffect, useRef, useState } from 'react'

/** An element's content box (width and height), kept current as it resizes. 0 × 0 until measured. */
export function useBox<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [box, setBox] = useState({ w: 0, h: 0 })

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      setBox((b) => (b.w === width && b.h === height ? b : { w: width, h: height }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  return [ref, box] as const
}
