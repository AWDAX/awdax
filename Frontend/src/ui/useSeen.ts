import { useInView } from 'motion/react'
import type { RefObject } from 'react'

/** True once the element has come into view, and stays true. Drives highlights that play on arrival. */
export function useSeen(ref: RefObject<Element | null>, amount = 0.35) {
  return useInView(ref, { once: true, amount })
}
