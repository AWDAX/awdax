import { OTHER_KEY } from '../../../analytics/aggregate.ts'
import { div, fromInt, mul, sum } from '../../../analytics/decimal.ts'
import { formatDec } from '../../../analytics/format.ts'
import type { Datum, Formatters } from './scale.ts'

// One hue, dark to light (tokens.css "Charts"): the largest share is the darkest. Never a rainbow.
const RAMP = ['stroke-ramp-5', 'stroke-ramp-4', 'stroke-ramp-3', 'stroke-ramp-2', 'stroke-ramp-1']
const SWATCH = ['bg-ramp-5', 'bg-ramp-4', 'bg-ramp-3', 'bg-ramp-2', 'bg-ramp-1']
// A donut is a thick ring; a pie is the same circle drawn with a stroke as wide as its diameter, so the slices
// meet in the middle (the total then moves to the legend).
const RING = { r: 52, stroke: 18 }
const PIE = { r: 30, stroke: 60 }

type Props = { data: Datum[]; fmt: Formatters; height: number; selected?: Set<string>; onSelect?: (key: string) => void; pie?: boolean }

/** Part-to-whole with an exact legend: value and share to two decimals. Negative values can't be shares. */
export function Donut({ data, fmt, height, selected, onSelect, pie = false }: Props) {
  const { r: R, stroke: STROKE } = pie ? PIE : RING
  const C = 2 * Math.PI * R
  const parts = data.filter((d) => d.v > 0)
  const total = sum(parts.map((d) => d.value))
  const totalV = parts.reduce((a, d) => a + d.v, 0)
  const lengths = parts.map((d) => (totalV ? (d.v / totalV) * C : 0))
  const starts = lengths.map((_, i) => lengths.slice(0, i).reduce((a, b) => a + b, 0))
  const tone = (i: number, key: string, kind: 'stroke' | 'bg') => {
    if (selected && selected.size > 0 && !selected.has(key)) return kind === 'stroke' ? 'stroke-line' : 'bg-line'
    if (key === OTHER_KEY) return kind === 'stroke' ? 'stroke-other' : 'bg-other'
    return (kind === 'stroke' ? RAMP : SWATCH)[Math.min(i, RAMP.length - 1)]
  }
  const size = Math.max(96, Math.min(160, height - 16))

  return (
    <div className="flex h-full flex-wrap items-center gap-5" style={{ minHeight: Math.min(height, 180) }} aria-hidden>
      <div className="relative shrink-0" style={{ width: size, height: size }}>
        <svg viewBox="0 0 128 128" className="size-full -rotate-90">
          <circle cx="64" cy="64" r={R} fill="none" className="stroke-sunken" strokeWidth={STROKE} />
          {parts.map((d, i) => (
            <circle
              key={d.key}
              cx="64"
              cy="64"
              r={R}
              fill="none"
              strokeWidth={STROKE}
              className={`${tone(i, d.key, 'stroke')} transition-[stroke-dasharray,stroke-dashoffset] duration-700 ease-soft`}
              style={{ strokeDasharray: `${lengths[i] > 0 ? Math.max(1.5, lengths[i] - (pie ? 0.8 : 2)) : 0} ${C}`, strokeDashoffset: -starts[i] }}
            />
          ))}
        </svg>
        {!pie && (
          <div className="absolute inset-0 grid place-content-center px-3 text-center">
            <span className="font-mono text-small font-medium break-all text-ink tabular-nums">{fmt.exact(total)}</span>
            <span className="text-micro text-ink-3">total</span>
          </div>
        )}
      </div>
      <ul className="flex min-w-0 flex-1 flex-col gap-1 text-small">
        {pie && (
          <li className="flex items-baseline justify-between gap-2 border-b border-line px-1 pb-1 text-micro text-ink-3">
            Total <span className="font-mono text-ink tabular-nums">{fmt.exact(total)}</span>
          </li>
        )}
        {parts.map((d, i) => (
          <li key={d.key}>
            <button
              type="button"
              tabIndex={-1}
              disabled={!onSelect || d.key === OTHER_KEY}
              onClick={() => onSelect?.(d.key)}
              className="flex w-full flex-wrap items-center gap-x-2 rounded-sm px-1 py-0.5 text-left hover:bg-sunken disabled:hover:bg-transparent"
            >
              <span className={`size-2.5 shrink-0 rounded-[3px] ${tone(i, d.key, 'bg')}`} />
              <span className="min-w-0 flex-1 truncate text-ink-2">{d.label}</span>
              <span className="ml-auto font-mono text-micro whitespace-nowrap text-ink-2 tabular-nums">
                {fmt.exact(d.value)} · {formatDec(div(mul(d.value, fromInt(100)), total, 2))}%
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
