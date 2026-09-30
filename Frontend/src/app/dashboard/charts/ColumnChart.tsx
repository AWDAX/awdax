import { useState } from 'react'
import { useWidth } from '../../../product/chart/useWidth.ts'
import { OTHER_KEY } from '../../../analytics/aggregate.ts'
import { ChartTip } from './ChartTip.tsx'
import { barTone, HALO, spaced, ticksFor } from './scale.ts'
import type { Datum, Formatters } from './scale.ts'

export type BarProps = {
  data: Datum[]
  fmt: Formatters
  height: number
  /** Print the exact value on each bar. */
  labels?: boolean
  /** Keys picked for cross-filtering: drawn in signal yellow, the rest stay ink. */
  selected?: Set<string>
  onSelect?: (key: string) => void
}

// Value labels print above the columns, so they get room at the top.
const PAD = { top: 12, labelTop: 24, right: 8, bottom: 28, left: 52 }

/** Vertical columns from a shared baseline (below it for negatives). Click a column to filter the dashboard. */
export function ColumnChart({ data, fmt, height, labels, selected, onSelect }: BarProps) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)
  const top = labels ? PAD.labelTop : PAD.top
  const plotW = Math.max(0, width - PAD.left - PAD.right)
  const plotH = Math.max(10, height - top - PAD.bottom)
  const axis = ticksFor(Math.min(...data.map((d) => d.v)), Math.max(...data.map((d) => d.v)), plotH)
  const lo = axis[0]
  const hi = axis[axis.length - 1]
  const y = (v: number) => top + plotH - ((v - lo) / (hi - lo || 1)) * plotH
  const slot = data.length ? plotW / data.length : 0
  const barW = Math.max(2, Math.min(48, slot * 0.68))
  const short = (s: string) => (s.length > 12 ? `${s.slice(0, 11)}…` : s)
  const centers = data.map((_, i) => PAD.left + slot * i + slot / 2)
  // Labels only where they fit; the exact value of every bar is in its tooltip and the Data tab.
  const axisShown = spaced(centers, data.map((d) => short(d.label)), 8)
  const valueShown = labels ? spaced(centers, data.map((d) => fmt.exact(d.value)), 4) : new Set<number>()

  return (
    <div ref={ref} className="relative w-full" style={{ height }} aria-hidden>
      {width > 0 && (
        <svg width={width} height={height} className="block">
          {axis.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={width - PAD.right} y1={y(t)} y2={y(t)} className={t === 0 ? 'stroke-ink' : 'stroke-line'} strokeWidth={t === 0 ? 1.5 : 1} />
              <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 font-mono text-micro tabular-nums">
                {fmt.tick(t, Math.max(Math.abs(lo), Math.abs(hi)))}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const cx = PAD.left + slot * i + slot / 2
            const barTop = y(Math.max(0, d.v))
            const h = Math.abs(y(d.v) - y(0))
            return (
              <g key={d.key}>
                <rect
                  x={cx - barW / 2}
                  y={barTop}
                  width={barW}
                  height={Math.max(h, d.v === 0 ? 0 : 1)}
                  rx={2}
                  strokeWidth={1.5}
                  className={`${barTone(d.key, selected)} transition-[y,height,fill] duration-500 ease-soft`}
                />
                {valueShown.has(i) && (
                  <text x={cx} y={barTop - 6} textAnchor="middle" className="fill-ink font-mono text-micro tabular-nums" style={HALO}>
                    {fmt.exact(d.value)}
                  </text>
                )}
                {axisShown.has(i) && (
                  <text x={cx} y={height - 8} textAnchor="middle" className="fill-ink-3 font-mono text-micro">
                    {short(d.label)}
                  </text>
                )}
                <rect
                  x={PAD.left + slot * i}
                  y={top}
                  width={slot}
                  height={plotH}
                  fill="transparent"
                  className={onSelect ? 'cursor-pointer' : undefined}
                  onPointerEnter={() => setHover(i)}
                  onPointerLeave={() => setHover(null)}
                  onClick={() => d.key !== OTHER_KEY && onSelect?.(d.key)}
                />
              </g>
            )
          })}
        </svg>
      )}
      {hover !== null && data[hover] && (
        <ChartTip x={PAD.left + slot * hover + slot / 2} y={y(Math.max(0, data[hover].v))}>
          {data[hover].label}: {fmt.exact(data[hover].value)} · {data[hover].count} rows
        </ChartTip>
      )}
    </div>
  )
}
