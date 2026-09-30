import type { ChartSpec } from '../../domain/charts.ts'

// Ordered levels, highest first, take the one-hue ramp from dark to light (tokens.css, "Charts").
const RAMP = ['stroke-ramp-5', 'stroke-ramp-4', 'stroke-ramp-3', 'stroke-ramp-2', 'stroke-ramp-1']
const SWATCH = ['bg-ramp-5', 'bg-ramp-4', 'bg-ramp-3', 'bg-ramp-2', 'bg-ramp-1']

const R = 52
const STROKE = 16
const C = 2 * Math.PI * R
const GAP = 2 // surface gap between segments, in px along the ring

/** Part-to-whole for a few ordered levels. Always has a legend with counts, so color never works alone. */
export function DonutChart({ spec, compact = false }: { spec: ChartSpec; compact?: boolean }) {
  const total = spec.data.reduce((n, d) => n + d.value, 0)
  const tone = (i: number, key: string) => (key === '__other' ? 'stroke-other' : RAMP[Math.min(i, RAMP.length - 1)])
  const swatch = (i: number, key: string) => (key === '__other' ? 'bg-other' : SWATCH[Math.min(i, SWATCH.length - 1)])
  const lengths = spec.data.map((d) => (total ? (d.value / total) * C : 0))
  const starts = lengths.map((_, i) => lengths.slice(0, i).reduce((a, b) => a + b, 0))

  return (
    <div className="flex items-center gap-6" aria-hidden>
      <div className={`relative shrink-0 ${compact ? 'size-28' : 'size-36'}`}>
        <svg viewBox="0 0 128 128" className="size-full -rotate-90">
          <circle cx="64" cy="64" r={R} fill="none" className="stroke-sunken" strokeWidth={STROKE} />
          {spec.data.map((d, i) => (
            <circle
              key={d.key}
              cx="64"
              cy="64"
              r={R}
              fill="none"
              strokeWidth={STROKE}
              className={`${tone(i, d.key)} transition-[stroke-dasharray,stroke-dashoffset] duration-700 ease-soft`}
              style={{
                // A tiny share keeps a sliver rather than vanishing while the legend still counts it.
                strokeDasharray: `${lengths[i] > 0 ? Math.max(1.5, lengths[i] - GAP) : 0} ${C}`,
                strokeDashoffset: -starts[i],
              }}
            />
          ))}
        </svg>
        <div className="absolute inset-0 grid place-content-center text-center">
          <span className="text-h3 font-medium text-ink tabular-nums">{total}</span>
          <span className="text-micro text-ink-3">rows</span>
        </div>
      </div>

      <ul className="flex min-w-0 flex-col gap-1.5 text-small">
        {spec.data.map((d, i) => (
          <li key={d.key} className="flex items-center gap-2">
            <span className={`size-2.5 shrink-0 rounded-[3px] ${swatch(i, d.key)}`} />
            <span className="truncate text-ink-2">{d.label}</span>
            <span className="ml-auto pl-3 font-mono text-micro text-ink-2 tabular-nums">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
