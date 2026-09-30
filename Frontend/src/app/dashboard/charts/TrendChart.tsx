import { useState } from 'react'
import type { PointerEvent } from 'react'
import { useWidth } from '../../../product/chart/useWidth.ts'
import { ChartTip } from './ChartTip.tsx'
import { HALO, spaced, ticksFor } from './scale.ts'
import type { Datum, Formatters } from './scale.ts'

type Props = {
  data: Datum[]
  fmt: Formatters
  height: number
  area?: boolean
  labels?: boolean
  /** Each point's place on a continuous timeline (months, quarters, days…). Null spaces points evenly. */
  positions?: (number | null)[]
  /** Break the line where a whole period is missing (months, quarters, years), rather than join across it. */
  breakGaps?: boolean
}

// Value labels print above the points, so they get room at the top.
const PAD = { top: 14, labelTop: 26, right: 16, bottom: 26, left: 56 }

/**
 * A value over time: ink line, yellow wash for the area variant. Points sit at their real place in time, so a
 * missing month is a visible gap, never a squeezed-out one. The nearest point follows the pointer.
 */
export function TrendChart({ data, fmt, height, area = false, labels, positions, breakGaps = false }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const top = labels ? PAD.labelTop : PAD.top
  const n = data.length
  const plotW = Math.max(0, width - PAD.left - PAD.right)
  const plotH = Math.max(10, height - top - PAD.bottom)
  const axis = ticksFor(Math.min(...data.map((d) => d.v)), Math.max(...data.map((d) => d.v)), plotH)
  const lo = axis[0]
  const hi = axis[axis.length - 1]
  const timed = positions && positions.length === n && positions.every((p) => p !== null) ? (positions as number[]) : null
  const t0 = timed ? Math.min(...timed) : 0
  const t1 = timed ? Math.max(...timed) : 0
  const x = (i: number) =>
    PAD.left + (n === 1 ? plotW / 2 : timed ? ((timed[i] - t0) / (t1 - t0 || 1)) * plotW : (i / (n - 1)) * plotW)
  const y = (v: number) => top + plotH - ((v - lo) / (hi - lo || 1)) * plotH
  const pts = data.map((d, i) => [x(i), y(d.v)] as const)

  // Split into runs at gaps: a missing period ends one run and starts the next.
  const runs: number[][] = []
  pts.forEach((_, i) => {
    const gap = breakGaps && timed && i > 0 && timed[i] - timed[i - 1] > 1
    if (i === 0 || gap) runs.push([i])
    else runs[runs.length - 1].push(i)
  })
  const path = (run: number[]) => run.map((i, k) => `${k ? 'L' : 'M'}${pts[i][0].toFixed(1)},${pts[i][1].toFixed(1)}`).join(' ')
  const base = y(Math.max(lo, Math.min(hi, 0)))
  const fill = (run: number[]) => `${path(run)} L${pts[run[run.length - 1]][0].toFixed(1)},${base} L${pts[run[0]][0].toFixed(1)},${base} Z`
  // Axis and value labels only where they fit, first and last always; every value is in the tooltip anyway.
  const xs = pts.map(([px]) => px)
  const axisShown = spaced(xs, data.map((d) => d.label), 14, true)
  const valueShown = labels ? spaced(xs, data.map((d) => fmt.exact(d.value)), 10, true) : new Set<number>()

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const px = e.clientX - e.currentTarget.getBoundingClientRect().left + PAD.left
    let best = 0
    pts.forEach(([ptx], i) => {
      if (Math.abs(ptx - px) < Math.abs(pts[best][0] - px)) best = i
    })
    setHover(best)
  }

  return (
    <div ref={ref} className="relative w-full" style={{ height }} aria-hidden>
      {width > 0 && n > 0 && (
        <svg width={width} height={height} className="block overflow-visible">
          {axis.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className={t === 0 ? 'stroke-ink' : 'stroke-line'} strokeWidth={t === 0 ? 1.5 : 1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 font-mono text-micro tabular-nums">
                {fmt.tick(t, Math.max(Math.abs(lo), Math.abs(hi)))}
              </text>
            </g>
          ))}
          {data.map((d, i) =>
            axisShown.has(i) ? (
              <text key={d.key} x={x(i)} y={height - 6} textAnchor={n > 1 && i === 0 ? 'start' : n > 1 && i === n - 1 ? 'end' : 'middle'} className="fill-ink-3 font-mono text-micro">
                {d.label}
              </text>
            ) : null,
          )}
          {area && runs.filter((r) => r.length > 1).map((r) => <path key={`f${r[0]}`} d={fill(r)} className="fill-series-wash" />)}
          {runs.map((r) => (
            <path key={`l${r[0]}`} d={path(r)} className="fill-none stroke-series" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {pts.map(([px, py], i) => (
            <circle key={data[i].key} cx={px} cy={py} r={hover === i ? 5 : n > 48 ? 1.5 : 3} className="fill-series stroke-surface" strokeWidth={2} />
          ))}
          {labels &&
            pts.map(([px, py], i) =>
              valueShown.has(i) ? (
                <text key={`v${data[i].key}`} x={px} y={py - 9} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} className="fill-ink font-mono text-micro tabular-nums" style={HALO}>
                  {fmt.exact(data[i].value)}
                </text>
              ) : null,
            )}
          {hover !== null && <line x1={pts[hover][0]} x2={pts[hover][0]} y1={top} y2={top + plotH} className="stroke-line-strong" strokeWidth={1} />}
          <rect x={PAD.left} y={top} width={plotW} height={plotH} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
        </svg>
      )}
      {hover !== null && data[hover] && (
        <ChartTip x={pts[hover][0]} y={pts[hover][1]} below={pts[hover][1] < 40}>
          {data[hover].label}: {fmt.exact(data[hover].value)} · {data[hover].count} {data[hover].count === 1 ? 'row' : 'rows'}
        </ChartTip>
      )}
    </div>
  )
}
