import { useEffect, useRef, useState } from 'react'
import { m, useReducedMotion } from 'motion/react'

export type AssistantOrbSize = 'sm' | 'md' | 'lg'

export type AssistantOrbProps = {
  /** Breathes (slow scale) while true; still when idle. */
  working?: boolean
  size?: AssistantOrbSize
  /** Set to give it meaning to assistive tech; otherwise it's decorative. */
  label?: string
  className?: string
}

const SIZE: Record<AssistantOrbSize, number> = { sm: 24, md: 32, lg: 48 }
const MIN_BLINK_MS = 4000
const MAX_BLINK_MS = 6000

/** Our own design: a small ink-on-signal orb with two blinking eyes, breathing gently while
 * `working`. No code copied; behaviour only inspired by OdysseyUI's assistant avatar. */
export function AssistantOrb({ working = false, size = 'md', label, className = '' }: AssistantOrbProps) {
  const reduceMotion = useReducedMotion()
  const [blink, setBlink] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (reduceMotion) return undefined
    const scheduleBlink = () => {
      const delay = MIN_BLINK_MS + Math.random() * (MAX_BLINK_MS - MIN_BLINK_MS)
      timeoutRef.current = setTimeout(() => {
        setBlink(true)
        setTimeout(() => setBlink(false), 120)
        scheduleBlink()
      }, delay)
    }
    scheduleBlink()
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [reduceMotion])

  const px = SIZE[size]
  const eyeH = blink ? 1 : Math.max(2, Math.round(px * 0.12))
  const eyeW = Math.max(2, Math.round(px * 0.12))
  const gap = Math.round(px * 0.22)

  return (
    <m.span
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      animate={working && !reduceMotion ? { scale: [1, 1.04, 1] } : { scale: 1 }}
      transition={working && !reduceMotion ? { duration: 3, repeat: Infinity, ease: 'easeInOut' } : { duration: 0.3 }}
      style={{ width: px, height: px }}
      className={`inline-flex items-center justify-center rounded-panel border-2 border-ink bg-signal ${className}`}
    >
      <span style={{ width: eyeW, height: eyeH, marginRight: gap / 2 }} className="rounded-control bg-ink transition-[height] duration-100" />
      <span style={{ width: eyeW, height: eyeH, marginLeft: gap / 2 }} className="rounded-control bg-ink transition-[height] duration-100" />
    </m.span>
  )
}
