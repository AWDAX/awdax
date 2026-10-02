import { useEffect, useRef } from 'react'
import type { KeyboardEvent, PointerEvent as ReactPointerEvent } from 'react'
import { SIDEBAR_DEFAULT, SIDEBAR_MAX, SIDEBAR_MIN, clampWidth } from './sidebarWidth.ts'

type Props = {
  width: number
  onChange: (px: number) => void
  /** True while a pointer drag is under way, so the column can drop its width transition and follow the cursor. */
  onDragging: (dragging: boolean) => void
}

const STEP = 16

/**
 * The sidebar's right edge, draggable to resize it. The pointer-capture drag is copied from the corner resize in
 * dashboard/Tile.tsx. Arrow keys nudge it, Home and End jump to the bounds, and a double-click resets it.
 */
export function SidebarResizer({ width, onChange, onDragging }: Props) {
  const start = useRef<{ x: number; w: number } | null>(null)

  // Unmounted mid-drag (the window narrowed to the phone layout, a hot reload): the body must not keep the
  // resize cursor, and the column must get its width transition back.
  useEffect(() => {
    const drag = start
    return () => {
      if (!drag.current) return
      document.body.style.removeProperty('cursor')
      document.body.style.removeProperty('user-select')
      onDragging(false)
    }
  }, [onDragging])

  const end = () => {
    if (!start.current) return
    start.current = null
    document.body.style.removeProperty('cursor')
    document.body.style.removeProperty('user-select')
    onDragging(false)
  }
  const onDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return
    e.preventDefault()
    e.currentTarget.setPointerCapture(e.pointerId)
    start.current = { x: e.clientX, w: width }
    // On the body too, so the cursor and the no-select hold while the pointer runs ahead of the edge.
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    onDragging(true)
  }
  const onMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const s = start.current
    if (s) onChange(clampWidth(s.w + e.clientX - s.x))
  }
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const steps: Partial<Record<string, number>> = { ArrowLeft: width - STEP, ArrowRight: width + STEP, Home: SIDEBAR_MIN, End: SIDEBAR_MAX }
    const next = steps[e.key]
    if (next === undefined) return
    e.preventDefault()
    onChange(clampWidth(next))
  }

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize sidebar"
      aria-valuemin={SIDEBAR_MIN}
      aria-valuemax={SIDEBAR_MAX}
      aria-valuenow={width}
      tabIndex={0}
      title="Drag to resize, double-click to reset"
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={end}
      onDoubleClick={() => onChange(SIDEBAR_DEFAULT)}
      onKeyDown={onKey}
      className="group absolute inset-y-0 right-0 z-30 w-2 cursor-col-resize touch-none outline-none"
    >
      {/* The 2px border thickens to 4px under the pointer, while dragging, and on keyboard focus. */}
      <span
        aria-hidden
        className="absolute inset-y-0 right-0 w-1 bg-ink opacity-0 transition-opacity duration-300 ease-soft group-hover:opacity-100 group-focus-visible:opacity-100 group-active:opacity-100"
      />
    </div>
  )
}
