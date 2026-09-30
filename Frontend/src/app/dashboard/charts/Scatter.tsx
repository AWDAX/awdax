import { useState } from 'react'
import { useWidth } from '../../../product/chart/useWidth.ts'
import { toNumber } from '../../../analytics/decimal.ts'
import type { Dec } from '../../../analytics/decimal.ts'
import { ChartTip } from './ChartTip.tsx'
import { niceTicks } from './scale.ts'

type Point = { row: number; x: Dec; y: Dec; label: string }
type Props = {
  points: Point[]
  height: number
  xLabel: string
  yLabel: string
  fmtX: (d: Dec) => string
  fmtY: (d: Dec) => string
  tickX: (t: number, top: number) => string
  tickY: (t: number, top: number) => string
}

const PAD = { top: 12, right: 16, bottom: 40, left: 56 }

/** Two measures against each other, one ink dot per row. Hover names the row and both exact values. */
export function Scatter({ points, height, xLabel, yLabel, fmtX, fmtY, tickX, tickY }: Props) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const xs = points.map((p) => toNumber(p.x))
  const ys = points.map((p) => toNumber(p.y))
  const ax = niceTicks(Math.min(...xs), Math.max(...xs))
  const ay = niceTicks(Math.min(...ys), Math.max(...ys))
  const plotW = Math.max(0, width - PAD.left - PAD.right)
  const plotH = height - PAD.top - PAD.bottom
  const sx = (v: number) => PAD.left + ((v - ax[0]) / (ax[ax.length - 1] - ax[0] || 1)) * plotW
  const sy = (v: number) => PAD.top + plotH - ((v - ay[0]) / (ay[ay.length - 1] - ay[0] || 1)) * plotH

  return (
    <div ref={ref} className="relative w-full" style={{ height }} aria-hidden>
      {width > 0 && (
        <svg width={width} height={height} className="block overflow-visible">
          {ay.map((t) => (
            <g key={`y${t}`}>
              <line x1={PAD.left} x2={width - PAD.right} y1={sy(t)} y2={sy(t)} className="stroke-line" />
              <text x={PAD.left - 8} y={sy(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 font-mono text-micro tabular-nums">
                {tickY(t, Math.max(Math.abs(ay[0]), Math.abs(ay[ay.length - 1])))}
              </text>
            </g>
          ))}
          {ax.map((t) => (
            <text key={`x${t}`} x={sx(t)} y={PAD.top + plotH + 16} textAnchor="middle" className="fill-ink-3 font-mono text-micro tabular-nums">
              {tickX(t, Math.max(Math.abs(ax[0]), Math.abs(ax[ax.length - 1])))}
            </text>
          ))}
          <text x={PAD.left + plotW / 2} y={height - 4} textAnchor="middle" className="fill-ink-2 text-micro">
            {xLabel}
          </text>
          <text x={12} y={PAD.top + plotH / 2} textAnchor="middle" transform={`rotate(-90 12 ${PAD.top + plotH / 2})`} className="fill-ink-2 text-micro">
            {yLabel}
          </text>
          {points.map((p, i) => (
            <circle
              key={p.row}
              cx={sx(xs[i])}
              cy={sy(ys[i])}
              r={hover === i ? 6 : 4}
              className={hover === i ? 'fill-signal stroke-ink' : 'fill-series stroke-surface'}
              fillOpacity={hover === i ? 1 : 0.7}
              strokeWidth={1.5}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
      )}
      {hover !== null && points[hover] && (
        <ChartTip x={sx(xs[hover])} y={sy(ys[hover])}>
          {points[hover].label} · {fmtX(points[hover].x)}, {fmtY(points[hover].y)}
        </ChartTip>
      )}
    </div>
  )
}
