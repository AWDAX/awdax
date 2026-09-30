import { useState } from 'react'
import { OTHER_KEY } from '../../../analytics/aggregate.ts'
import type { BarProps } from './ColumnChart.tsx'
import { barTone } from './scale.ts'

/**
 * Horizontal bars, one row per group, exact value at the tip. Best for long names and rankings.
 * Negative values draw left of a zero line.
 */
export function BarChart({ data, fmt, height, selected, onSelect }: BarProps) {
  const [hover, setHover] = useState<string | null>(null)
  const maxAbs = Math.max(1e-12, ...data.map((d) => Math.abs(d.v)))
  const hasNeg = data.some((d) => d.v < 0)
  const rowH = Math.max(18, Math.min(30, (height - 8) / Math.max(1, data.length)))

  return (
    <ul className="scrollbar-none flex flex-col overflow-y-auto" style={{ maxHeight: height }} aria-hidden data-lenis-prevent>
      {data.map((d) => {
        // Lengths stay strictly proportional; the longest bar leaves room for its value label.
        const pct = (Math.abs(d.v) / maxAbs) * (hasNeg ? 48 : 78)
        const tone = barTone(d.key, selected).replace(/fill-/g, 'bg-').replace('stroke-ink', 'outline-1 outline-ink')
        return (
          <li key={d.key} style={{ height: rowH }}>
            <button
              type="button"
              tabIndex={-1}
              disabled={!onSelect || d.key === OTHER_KEY}
              onClick={() => onSelect?.(d.key)}
              onPointerEnter={() => setHover(d.key)}
              onPointerLeave={() => setHover(null)}
              className={`grid h-full w-full grid-cols-[minmax(0,9rem)_minmax(0,1fr)] items-center gap-3 rounded-sm px-1 text-left text-small ${hover === d.key ? 'bg-sunken' : ''} disabled:cursor-default`}
            >
              <span className="truncate text-ink-2" title={d.label}>
                {d.label}
              </span>
              <span className={`flex items-center gap-2 ${hasNeg ? 'justify-center' : ''}`}>
                <span className={`flex ${hasNeg ? 'w-1/2 justify-end' : 'hidden'}`}>
                  {d.v < 0 && <span className={`h-3 rounded-l-sm ${tone}`} style={{ width: `${pct * 2}%` }} />}
                </span>
                <span className={`flex items-center gap-2 ${hasNeg ? 'w-1/2' : 'w-full'}`}>
                  {d.v >= 0 && (
                    <span className={`h-3 shrink-0 rounded-r-sm transition-[width] duration-500 ease-soft ${tone}`} style={{ width: `${hasNeg ? pct * 2 : pct}%` }} />
                  )}
                  <span className="font-mono text-micro whitespace-nowrap text-ink-2 tabular-nums">
                    {fmt.exact(d.value)}
                    {hover === d.key && <span className="text-ink-3"> · {d.count} rows</span>}
                  </span>
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
