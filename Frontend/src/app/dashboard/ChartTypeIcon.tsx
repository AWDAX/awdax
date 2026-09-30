import type { ReactNode } from 'react'
import type { ChartType } from '../../analytics/spec.ts'

// Small pictures of each chart type for the "Add charts" gallery and the builder, drawn in currentColor on a
// 40 × 28 grid (a lighter tint of the same colour for the "rest" of a whole). Hand-drawn, not from a library.
const soft = { fill: 'currentColor', fillOpacity: 0.22 }
const solid = { fill: 'currentColor' }
const line = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' } as const

const GLYPH: Record<ChartType, ReactNode> = {
  column: (
    <>
      <rect x="5" y="14" width="6" height="11" rx="1" {...solid} />
      <rect x="14" y="6" width="6" height="19" rx="1" {...solid} />
      <rect x="23" y="10" width="6" height="15" rx="1" {...solid} />
      <rect x="32" y="18" width="4" height="7" rx="1" {...soft} />
    </>
  ),
  bar: (
    <>
      <rect x="4" y="4" width="30" height="5" rx="1" {...solid} />
      <rect x="4" y="11.5" width="22" height="5" rx="1" {...solid} />
      <rect x="4" y="19" width="13" height="5" rx="1" {...soft} />
    </>
  ),
  line: (
    <>
      <polyline points="4,21 12,15 19,18 27,8 36,11" {...line} />
      {[
        [4, 21],
        [12, 15],
        [19, 18],
        [27, 8],
        [36, 11],
      ].map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="2" {...solid} />
      ))}
    </>
  ),
  area: (
    <>
      <polygon points="4,24 4,19 12,13 19,16 27,6 36,10 36,24" {...soft} />
      <polyline points="4,19 12,13 19,16 27,6 36,10" {...line} />
    </>
  ),
  pie: (
    <>
      <circle cx="20" cy="14" r="11" {...soft} />
      <path d="M20 14 L20 3 A11 11 0 0 1 30.4 17.6 Z" {...solid} />
    </>
  ),
  donut: (
    <>
      <circle cx="20" cy="14" r="9" fill="none" stroke="currentColor" strokeOpacity={0.22} strokeWidth="5" />
      <path d="M20 5 A9 9 0 1 1 11.4 16.8" fill="none" stroke="currentColor" strokeWidth="5" />
    </>
  ),
  scatter: (
    <>
      {[
        [7, 20],
        [11, 15],
        [16, 17],
        [20, 10],
        [25, 12],
        [29, 6],
        [33, 8],
      ].map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="2.4" {...solid} />
      ))}
    </>
  ),
  kpi: (
    <text x="20" y="20" textAnchor="middle" className="font-display font-extrabold" fontSize="15" {...solid}>
      123
    </text>
  ),
  table: (
    <>
      <rect x="4" y="4" width="32" height="20" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect x="4" y="4" width="32" height="5" {...soft} />
      <path d="M4 14h32M4 19h32M16 4v20" stroke="currentColor" strokeWidth="1.2" />
    </>
  ),
}

/** A picture of a chart type, e.g. for a gallery tile. Decorative: pair it with the type's name. */
export function ChartTypeIcon({ type, className = '' }: { type: ChartType; className?: string }) {
  return (
    <svg viewBox="0 0 40 28" aria-hidden className={className}>
      {GLYPH[type]}
    </svg>
  )
}
