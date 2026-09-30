import { useState } from 'react'
import type { ChartSpec } from '../../domain/charts.ts'
import { ticks } from './ticks.ts'
import { useWidth } from './useWidth.ts'

const PAD = { top: 12, right: 12, bottom: 22, left: 24 }
const MOVE = 'transition-[d,cx,cy] duration-700 ease-soft'

/** Count over time. The line rises from the baseline as rows arrive; the scale never moves. */
export function LineChart({ spec, height = 160 }: { spec: ChartSpec; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const axis = ticks(spec.max)
  const top = axis[axis.length - 1]
  const n = spec.data.length
  const plotW = Math.max(0, width - PAD.left - PAD.right)
  const plotH = height - PAD.top - PAD.bottom
  const x = (i: number) => PAD.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH
  const pts = spec.data.map((d, i) => [x(i), y(d.value)] as const)
  const line = pts.map(([px, py], i) => `${i ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)}`).join(' ')
  const area = `${line} L${x(n - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`
  const end = pts[n - 1]
  const every = Math.ceil(n / Math.max(2, Math.floor(plotW / 44)))

  return (
    <div ref={ref} className="relative w-full" style={{ height }} aria-hidden>
      {width > 0 && (
        <svg width={width} height={height} className="block overflow-visible">
          {axis.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className="stroke-line" strokeWidth={1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 font-mono text-micro tabular-nums">
                {t}
              </text>
            </g>
          ))}
          {spec.data.map((d, i) =>
            i % every === 0 || i === n - 1 ? (
              <text key={d.key} x={x(i)} y={height - 4} textAnchor="middle" className="fill-ink-3 font-mono text-micro">
                {d.label}
              </text>
            ) : null,
          )}
          {/* `d` and `cx`/`cy` transition as CSS properties; where a browser can't, the line just steps. */}
          <path d={area} className={`fill-series-wash ${MOVE}`} />
          <path
            d={line}
            className={`fill-none stroke-series ${MOVE}`}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {hover !== null && (
            <g>
              <line x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={y(0)} className="stroke-line-strong" strokeWidth={1} />
              <circle cx={pts[hover][0]} cy={pts[hover][1]} r={4} className="fill-series stroke-surface" strokeWidth={2} />
            </g>
          )}
          <circle cx={end[0]} cy={end[1]} r={4} className={`fill-series stroke-surface ${MOVE}`} strokeWidth={2} />
          {spec.data.map((d, i) => (
            <rect
              key={d.key}
              x={x(i) - plotW / Math.max(1, n - 1) / 2}
              y={PAD.top}
              width={plotW / Math.max(1, n - 1)}
              height={plotH}
              fill="transparent"
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
            />
          ))}
        </svg>
      )}
      {hover !== null && (
        <span
          className="pointer-events-none absolute -translate-x-1/2 -translate-y-full rounded-sm bg-ink px-1.5 py-0.5 font-mono text-micro whitespace-nowrap text-on-ink"
          style={{ left: pts[hover][0], top: pts[hover][1] - 8 }}
        >
          {spec.data[hover].label}: {spec.data[hover].value}
        </span>
      )}
    </div>
  )
}
