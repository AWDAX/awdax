import { useEffect, useState } from 'react'
import type { RefObject } from 'react'
import { m, useReducedMotion } from 'motion/react'
import type { Method } from '../../domain/types.ts'
import { METHOD } from '../../product/meta.ts'
import { EASE_DRAW, TRACE_S, TRACE_STAGGER_S } from '../../ui/motion.ts'

type Props = {
  /** The scene grid holding both the source page ([data-from]) and the row stream ([data-to]). */
  sceneRef: RefObject<HTMLElement | null>
  /**
   * Traces every [data-from] starting with "{rowId}:". Null draws nothing. In the hero it is the row
   * being read, set only once the row has landed; elsewhere any shared prefix works.
   */
  rowId: string | null
}

type Line = { key: string; method: Method; d: string; x: number; y: number }

/** Lets the row finish arriving (row-in settles its 8px rise by ~420ms) before measuring. */
const MEASURE_AFTER_MS = 450
const DRAW = { duration: TRACE_S, ease: EASE_DRAW }
const STAGGER = TRACE_STAGGER_S
const DOT_R = 3.5
/** The line stops just short of the cell, so its dot sits in the column gap, not on the first letter. */
const LAND_GAP = 5
/** Inside the table, lines run in the clear strip at the top of the row, above its text. */
const LANE_INSET = 4

const pt = (x: number, y: number) => `${x.toFixed(1)},${y.toFixed(1)}`

/**
 * From the end of a highlight (sx, sy) to just left of a cell (tx, ty). A line to the first column
 * is one cubic. A line to a later column enters the table in the row's top lane and drops into its
 * cell, so it never runs through the text of the cells before it: a line through text reads as
 * the red pen, which means "skipped".
 */
function route(sx: number, sy: number, tx: number, ty: number, tableX: number, lane: number): string {
  if (tx - tableX < LAND_GAP * 2) {
    const bend = (tx - sx) / 2
    return `M${pt(sx, sy)} C${pt(sx + bend, sy)} ${pt(tx - bend, ty)} ${pt(tx, ty)}`
  }
  const bend = (tableX - sx) / 2
  const hook = Math.max(0, ty - lane)
  return (
    `M${pt(sx, sy)} C${pt(sx + bend, sy)} ${pt(tableX - bend, lane)} ${pt(tableX, lane)}` +
    ` L${pt(tx - hook, lane)} Q${pt(tx, lane)} ${pt(tx, ty)}`
  )
}

function measure(scene: HTMLElement, rowId: string): Line[] {
  const box = scene.getBoundingClientRect()
  const lines: Line[] = []
  for (const from of scene.querySelectorAll<HTMLElement>(`[data-from^="${CSS.escape(rowId)}:"]`)) {
    const key = from.dataset.from!
    // Many sources can point at one target (rows merging) by naming it in data-target.
    const to = scene.querySelector<HTMLElement>(`[data-to="${CSS.escape(from.dataset.target ?? key)}"]`)
    if (!to) continue
    const target = to.getBoundingClientRect()
    // A cell hidden in a narrow table has no width: nothing to point at.
    if (target.width === 0) continue
    const row = (to.closest('[role="row"]') ?? to).getBoundingClientRect()
    // A highlight that wraps ends on its last line, so the line starts there.
    const rects = from.getClientRects()
    const end = rects[rects.length - 1] ?? from.getBoundingClientRect()
    const sx = end.right - box.left
    const sy = end.top + end.height / 2 - box.top
    const tableX = row.left - box.left - LAND_GAP
    const tx = target.left - box.left - LAND_GAP
    const ty = target.top + target.height / 2 - box.top
    // Stacked layout: the table sits below, not beside, the page.
    if (tableX <= sx) continue
    lines.push({
      key,
      method: (from.dataset.method as Method | undefined) ?? 'content',
      d: route(sx, sy, tx, ty, tableX, row.top - box.top + LANE_INSET),
      x: tx,
      y: ty,
    })
  }
  return lines
}

/**
 * Lines from each highlighted quote on the source page to the table cell it became: "came from here".
 * Wide screens only. Each line draws itself, then lands on a dot. Reduced motion shows them drawn.
 */
export function TraceLayer({ sceneRef, rowId }: Props) {
  const reduced = useReducedMotion() ?? false
  // Keyed by row, so the previous row's lines never flash while the next one is measured.
  const [traced, setTraced] = useState<{ rowId: string; lines: Line[] } | null>(null)

  useEffect(() => {
    const scene = sceneRef.current
    if (!rowId || !scene) return
    let ro: ResizeObserver | undefined
    const update = () => setTraced({ rowId, lines: measure(scene, rowId) })
    const id = setTimeout(() => {
      update()
      ro = new ResizeObserver(update)
      ro.observe(scene)
    }, MEASURE_AFTER_MS)
    return () => {
      clearTimeout(id)
      ro?.disconnect()
    }
  }, [rowId, sceneRef])

  const lines = traced && traced.rowId === rowId ? traced.lines : []

  return (
    <svg aria-hidden className="pointer-events-none absolute inset-0 hidden size-full overflow-visible lg:block">
      {lines.map((l, i) => {
        const delay = i * STAGGER
        return (
          <g key={`${rowId}-${l.key}`} className={METHOD[l.method].line}>
            <m.path
              d={l.d}
              fill="none"
              stroke="currentColor"
              strokeWidth={1.5}
              strokeLinecap="round"
              initial={reduced ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ ...DRAW, delay }}
            />
            <m.circle
              cx={l.x}
              cy={l.y}
              r={DOT_R}
              fill="currentColor"
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.3, delay: delay + DRAW.duration * 0.85 }}
            />
          </g>
        )
      })}
    </svg>
  )
}
