import type { ChartSpec } from '../domain/charts.ts'
import { BarsChart, ColumnsChart } from './chart/ColumnsChart.tsx'
import { DonutChart } from './chart/DonutChart.tsx'
import { LineChart } from './chart/LineChart.tsx'

type Props = {
  spec: ChartSpec
  /** Shorter drawings for dashboard tiles. The tile's own heading names the chart, so no caption here. */
  compact?: boolean
  className?: string
}

/**
 * One chart, chosen by column type (domain/charts.ts), with the sentence saying why.
 * The drawing is aria-hidden; the table below it carries the same numbers for screen readers.
 */
export function AutoChart({ spec, compact = false, className = '' }: Props) {
  const { missing, column } = spec
  return (
    <figure className={`@container flex flex-col gap-3 ${className}`}>
      {!compact && <figcaption className="text-small font-medium text-ink">{spec.title}</figcaption>}

      {spec.kind === 'line' && <LineChart spec={spec} height={compact ? 120 : undefined} />}
      {spec.kind === 'histogram' && <ColumnsChart spec={spec} height={compact ? 100 : undefined} />}
      {spec.kind === 'donut' && <DonutChart spec={spec} compact={compact} />}
      {spec.kind === 'bars' && <BarsChart spec={spec} compact={compact} />}

      <p className="text-micro text-ink-3">
        {spec.reason}
        {missing > 0 &&
          ` ${missing} ${missing === 1 ? 'row has' : 'rows have'} no ${column.label.toLowerCase()} and ${missing === 1 ? 'is' : 'are'} left out.`}
      </p>

      <table className="sr-only">
        <caption>{spec.title}</caption>
        <thead>
          <tr>
            <th scope="col">{spec.kind === 'line' ? 'Period' : column.label}</th>
            <th scope="col">Rows</th>
          </tr>
        </thead>
        <tbody>
          {spec.data.map((d) => (
            <tr key={d.key}>
              <th scope="row">{d.label}</th>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
