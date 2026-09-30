import { useState } from 'react'
import type { ChartSpec } from '../../domain/charts.ts'
import { ticks } from './ticks.ts'

/** Histogram: one vertical column per range, growing from a shared baseline. */
export function ColumnsChart({ spec, height = 140 }: { spec: ChartSpec; height?: number }) {
  const [hover, setHover] = useState<number | null>(null)
  const axis = ticks(spec.max)
  const top = axis[axis.length - 1]
  const last = spec.data.length - 1

  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2" aria-hidden>
      <div className="relative text-right font-mono text-micro text-ink-3 tabular-nums" style={{ height }}>
        {axis.map((t) => (
          <span key={t} className="absolute right-0 -translate-y-1/2" style={{ top: `${100 - (t / top) * 100}%` }}>
            {t}
          </span>
        ))}
      </div>

      <div className="relative" style={{ height }}>
        {axis.map((t) => (
          <span key={t} className="absolute inset-x-0 h-px bg-line" style={{ top: `${100 - (t / top) * 100}%` }} />
        ))}
        <div className="absolute inset-0 flex items-end gap-0.5">
          {spec.data.map((d, i) => (
            <div
              key={d.key}
              className="relative flex h-full flex-1 items-end justify-center"
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
            >
              <div
                className="w-full max-w-6 rounded-t-sm bg-series transition-[height] duration-700 ease-soft"
                style={{ height: `${(d.value / top) * 100}%` }}
              />
              {hover === i && (
                <span
                  className="absolute z-10 rounded-sm bg-ink px-1.5 py-0.5 font-mono text-micro whitespace-nowrap text-on-ink"
                  style={{ bottom: `calc(${(d.value / top) * 100}% + 6px)` }}
                >
                  {d.label}: {d.value}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>

      <span />
      <div className="mt-2 flex gap-0.5">
        {spec.data.map((d, i) => (
          <span
            key={d.key}
            className={`flex-1 truncate text-center font-mono text-micro text-ink-3 ${i === 0 || i === last ? '' : 'invisible @md:visible'}`}
          >
            {d.label}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Category or location counts: one horizontal bar per group, value at the tip. */
export function BarsChart({ spec, compact = false }: { spec: ChartSpec; compact?: boolean }) {
  return (
    <ul className={`flex flex-col ${compact ? 'gap-1' : 'gap-2'}`} aria-hidden>
      {spec.data.map((d) => (
        <li key={d.key} className="grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] items-center gap-3 text-small">
          <span className="truncate text-ink-2">{d.label}</span>
          <span className="flex items-center gap-2">
            <span
              className={`h-3 rounded-r-sm transition-[width] duration-700 ease-soft ${d.key === '__other' ? 'bg-other' : 'bg-series'}`}
              style={{ width: `${(d.value / spec.max) * 85}%` }}
            />
            <span className="font-mono text-micro text-ink-2 tabular-nums">{d.value}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
