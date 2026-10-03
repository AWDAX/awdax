import type { ReactNode } from 'react'

/** The hover label: ink box, exact value in Geist Mono. Positioned over the chart, never clipped by the SVG. */
export function ChartTip({ x, y, children, below = false }: { x: number; y: number; children: ReactNode; below?: boolean }) {
  return (
    <span
      role="presentation"
      className={`pointer-events-none absolute z-20 -translate-x-1/2 rounded-sm bg-ink px-2 py-1 font-mono text-micro whitespace-nowrap text-on-ink ${below ? 'translate-y-2' : '-translate-y-full'}`}
      style={{ left: x, top: below ? y : y - 8 }}
    >
      {children}
    </span>
  )
}

/**
 * Screen-reader copy of a chart's numbers; the drawing itself is aria-hidden. The sr-only box wraps the table: a
 * table won't shrink to sr-only's 1px, so on its own it stayed hundreds of pixels wide and pushed phones sideways.
 */
export function SrTable({ caption, head, rows }: { caption: string; head: [string, string]; rows: [string, string][] }) {
  return (
    <div className="sr-only">
      <table>
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th scope="col">{head[0]}</th>
            <th scope="col">{head[1]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([a, b], i) => (
            <tr key={i}>
              <th scope="row">{a}</th>
              <td>{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
