import { useLayoutEffect, useRef, useState } from 'react'
import type { ReactNode, RefObject } from 'react'
import { createPortal } from 'react-dom'

type Props = {
  /** The button the popover belongs to; it opens below it, or above when there's no room. */
  anchor: RefObject<HTMLElement | null>
  open: boolean
  onClose: () => void
  /** Line up with the anchor's left or right edge. */
  align?: 'start' | 'end'
  className?: string
  children: ReactNode
  /** Passed to the popover root, e.g. a focus-trap ref. */
  boxRef?: RefObject<HTMLDivElement | null>
  role?: string
  label?: string
}

const GAP = 6
const EDGE = 8

/**
 * A floating panel for menus and pickers, rendered at the end of <body> so no tile, card or scroll area can
 * clip it. It follows its anchor on scroll and resize, flips above when there's no room below, stays inside
 * the viewport, and closes on Escape or a click outside.
 */
export function Popover({ anchor, open, onClose, align = 'end', className = '', children, boxRef, role, label }: Props) {
  const own = useRef<HTMLDivElement>(null)
  const box = boxRef ?? own
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null)

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const a = anchor.current?.getBoundingClientRect()
      const el = box.current
      if (!a || !el) return
      const w = el.offsetWidth
      const h = el.offsetHeight
      let left = align === 'end' ? a.right - w : a.left
      left = Math.max(EDGE, Math.min(left, window.innerWidth - w - EDGE))
      const below = a.bottom + GAP
      const top = below + h > window.innerHeight - EDGE && a.top - GAP - h > EDGE ? a.top - GAP - h : Math.min(below, window.innerHeight - h - EDGE)
      setPos({ left, top: Math.max(EDGE, top) })
    }
    place()
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!box.current?.contains(t) && !anchor.current?.contains(t)) onClose()
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, anchor, box, align, onClose])

  if (!open) return null
  return createPortal(
    <div
      ref={box}
      role={role}
      aria-label={label}
      data-lenis-prevent
      className={`fixed z-50 rounded-panel border-2 border-ink bg-surface ${className}`}
      // Measured first while invisible, then placed, so it never flashes in the wrong spot.
      style={pos ? { left: pos.left, top: pos.top } : { left: 0, top: 0, visibility: 'hidden' }}
    >
      {children}
    </div>,
    document.body,
  )
}
