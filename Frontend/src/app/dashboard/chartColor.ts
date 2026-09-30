import type { CSSProperties } from 'react'
import type { ChartColor } from '../../analytics/spec.ts'

/** The colours a tile can take, in menu order. Ink is the default. */
export const CHART_COLORS: { key: ChartColor; label: string; swatch: string }[] = [
  // Swatch classes are written out in full so Tailwind finds them (and so emits each --color-chart-* token).
  { key: 'ink', label: 'Ink', swatch: 'bg-chart-ink' },
  { key: 'blue', label: 'Blue', swatch: 'bg-chart-blue' },
  { key: 'teal', label: 'Teal', swatch: 'bg-chart-teal' },
  { key: 'green', label: 'Green', swatch: 'bg-chart-green' },
  { key: 'orange', label: 'Orange', swatch: 'bg-chart-orange' },
  { key: 'purple', label: 'Purple', swatch: 'bg-chart-purple' },
  { key: 'pink', label: 'Pink', swatch: 'bg-chart-pink' },
]

/**
 * Re-points the chart tokens at one colour for everything inside a tile: the series (lines, columns, bars,
 * dots, the number card), the wash under an area, and the donut's ramp, mixed from that colour toward white,
 * darkest for the largest share. Ink (or unset) keeps the defaults: ink marks, yellow wash, grey ramp.
 */
export function chartColorStyle(color: ChartColor | undefined): CSSProperties | undefined {
  if (!color || color === 'ink') return undefined
  const hue = `var(--color-chart-${color})`
  const mix = (pct: number) => `color-mix(in oklab, ${hue} ${pct}%, var(--color-surface))`
  return {
    '--color-series': hue,
    '--color-series-wash': `color-mix(in oklab, ${hue} 22%, transparent)`,
    '--color-ramp-5': hue,
    '--color-ramp-4': mix(78),
    '--color-ramp-3': mix(58),
    '--color-ramp-2': mix(40),
    '--color-ramp-1': mix(24),
  } as CSSProperties
}
