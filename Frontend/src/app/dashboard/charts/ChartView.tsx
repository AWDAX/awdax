import { useMemo } from 'react'
import { AnimatePresence, m } from 'motion/react'
import { EASE_SOFT } from '../../../ui/motion.ts'
import { points as scatterPoints } from '../../../analytics/aggregate.ts'
import type { Filter, QueryResult } from '../../../analytics/aggregate.ts'
import { formatCompact, formatFor } from '../../../analytics/format.ts'
import { fromString } from '../../../analytics/decimal.ts'
import type { TableProfile } from '../../../analytics/profile.ts'
import type { ChartSpec } from '../../../analytics/spec.ts'
import { ordinal } from '../../../analytics/period.ts'
import { measureTitle } from '../../../analytics/suggest.ts'
import { DataGrid } from '../DataGrid.tsx'
import { BarChart } from './BarChart.tsx'
import { SrTable } from './ChartTip.tsx'
import { ColumnChart } from './ColumnChart.tsx'
import { Donut } from './Donut.tsx'
import { formattersFor, series } from './scale.ts'
import { Scatter } from './Scatter.tsx'
import { TrendChart } from './TrendChart.tsx'
import { useResult } from './useResult.ts'

type Props = {
  spec: ChartSpec
  profile: TableProfile
  /** Dashboard-wide filters (slicers, search, cross-filter from another tile). */
  filters?: Filter[]
  height: number
  selected?: Set<string>
  onSelect?: (key: string) => void
}

/** Draws one tile's chart from its spec. Every value on screen comes from the exact query result. */
export function ChartView({ spec, profile, filters = [], height, selected, onSelect }: Props) {
  const result = useResult(profile, spec, filters)
  const fmt = formattersFor(profile, result)
  const data = series(result)

  let content
  if (spec.type === 'scatter') {
    content = <ScatterTile spec={spec} profile={profile} filters={filters} height={height} />
  } else if (spec.type === 'kpi') {
    const text = fmt.exact(result.overall)
    // The whole exact number on one line: the type shrinks with the tile's width and height instead of wrapping.
    const px = Math.max(16, Math.round(height * 0.82))
    content = (
      <div className="@container flex items-center" style={{ height }} title={`${measureTitle(profile, result.query)}: ${text}`}>
        <p className="font-display font-wide leading-none font-extrabold whitespace-nowrap text-series tabular-nums" style={{ fontSize: `min(${px}px, 3rem, calc(165cqw / ${Math.max(5, text.length)}))` }}>
          {text}
        </p>
      </div>
    )
  } else if (spec.type === 'table' && spec.query.groupBy === undefined) {
    content = <DataGrid profile={profile} filters={filters} height={height} compact />
  } else if (data.length === 0) {
    content = <p className="grid place-items-center text-small text-ink-3" style={{ height }}>No rows with a value match these filters.</p>
  } else {
    const common = { data, fmt, height, labels: spec.labels, selected, onSelect }
    const groupCol = result.query.groupBy !== undefined ? profile.columns[result.query.groupBy] : undefined
    content = (
      <>
        {spec.type === 'column' && <ColumnChart {...common} />}
        {spec.type === 'bar' && <BarChart {...common} />}
        {(spec.type === 'line' || spec.type === 'area') && (
          <TrendChart
            data={data}
            fmt={fmt}
            height={height}
            area={spec.type === 'area'}
            labels={spec.labels}
            positions={groupCol?.kind === 'period' ? data.map((d) => ordinal(d.key)) : undefined}
            breakGaps={groupCol?.kind === 'period' && ['month', 'quarter', 'year', 'fiscal'].includes(result.query.bucket ?? groupCol.grain ?? '')}
          />
        )}
        {(spec.type === 'donut' || spec.type === 'pie') && <Donut data={data} fmt={fmt} height={height} selected={selected} onSelect={onSelect} pie={spec.type === 'pie'} />}
        {spec.type === 'table' && <ResultTable result={result} fmt={fmt.exact} groupLabel={groupCol?.label ?? 'Group'} height={height} />}
        <SrTable
          caption={spec.title}
          head={[groupCol?.label ?? 'Group', measureTitle(profile, result.query)]}
          rows={data.map((d) => [d.label, fmt.exact(d.value)])}
        />
      </>
    )
  }

  return (
    <AnimatePresence mode="wait">
      <m.div
        key={spec.type}
        initial={{ opacity: 0, scale: 0.98 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.98 }}
        transition={{ duration: 0.2, ease: EASE_SOFT }}
        className="h-full w-full"
      >
        {content}
      </m.div>
    </AnimatePresence>
  )
}

function ResultTable({ result, fmt, groupLabel, height }: { result: QueryResult; fmt: (d: QueryResult['overall']) => string; groupLabel: string; height: number }) {
  return (
    <div className="scrollbar-none overflow-auto" style={{ maxHeight: height }} data-lenis-prevent>
      <table className="w-full text-small">
        <thead className="sticky top-0 bg-surface">
          <tr className="border-b-2 border-ink text-left">
            <th className="py-1.5 pr-3 font-medium">{groupLabel}</th>
            <th className="py-1.5 pr-3 text-right font-medium">Value</th>
            <th className="py-1.5 text-right font-medium">Rows</th>
          </tr>
        </thead>
        <tbody>
          {result.rows.map((r) => (
            <tr key={r.key} className="border-b border-line">
              <td className="py-1.5 pr-3 text-ink-2">{r.label}</td>
              <td className="py-1.5 pr-3 text-right font-mono tabular-nums">{fmt(r.value)}</td>
              <td className="py-1.5 text-right font-mono text-ink-3 tabular-nums">{r.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ScatterTile({ spec, profile, filters, height }: { spec: ChartSpec; profile: TableProfile; filters: Filter[]; height: number }) {
  const cx = spec.x !== undefined ? profile.columns[spec.x] : undefined
  const cy = spec.y !== undefined ? profile.columns[spec.y] : undefined
  const pts = useMemo(() => (cx && cy ? scatterPoints(profile, cx.index, cy.index, filters) : { points: [], skipped: 0 }), [profile, cx, cy, filters])
  if (!cx || !cy || pts.points.length === 0) return <p className="text-small text-ink-3">Pick two number columns for a scatter.</p>
  // Name each dot by the first text-like column (a model, a company), else by its row number.
  const nameCol = profile.columns.find((c) => c.kind === 'text' || c.kind === 'category')
  const tick = (col: typeof cx) => (t: number, top: number) => {
    const d = fromString(String(t))
    return d ? formatCompact(d, { currency: col.currency, percent: col.percent }, fromString(String(top)) ?? undefined) : String(t)
  }
  return (
    <Scatter
      points={pts.points.map((p) => ({ ...p, label: nameCol?.labels[p.row] || `Row ${p.row + 1}` }))}
      height={height}
      xLabel={cx.label}
      yLabel={cy.label}
      fmtX={(d) => formatFor(cx, d)}
      fmtY={(d) => formatFor(cy, d)}
      tickX={tick(cx)}
      tickY={tick(cy)}
    />
  )
}
