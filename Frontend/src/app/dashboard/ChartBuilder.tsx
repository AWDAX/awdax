import { useState } from 'react'
import type { ReactNode } from 'react'
import { AGG_LABEL } from '../../analytics/aggregate.ts'
import type { Agg, Query, SortBy } from '../../analytics/aggregate.ts'
import { isGroupable, isMeasure } from '../../analytics/profile.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { CHART_LABEL } from '../../analytics/spec.ts'
import type { ChartSpec, ChartType } from '../../analytics/spec.ts'
import { queryTitle } from '../../analytics/suggest.ts'
import { Button } from '../../ui/Button.tsx'
import { Select } from '../../ui/Select.tsx'
import { ChartView } from './charts/ChartView.tsx'
import { draftFor, GALLERY, unavailable } from './chartTypes.ts'
import { ChartTypeIcon } from './ChartTypeIcon.tsx'

const field = 'h-9 w-full rounded-control border-2 border-line bg-surface px-2 text-small hover:border-ink focus-visible:border-ink focus-visible:outline-none'
const AGGS: Agg[] = ['sum', 'avg', 'median', 'min', 'max', 'count', 'distinct']

type Props = {
  profile: TableProfile
  initial?: ChartSpec
  /** Opened from a picture in the "Add charts" gallery: start as this chart type. */
  startType?: ChartType
  onSave: (spec: ChartSpec) => void
  onCancel: () => void
}

/**
 * Build any chart the table supports, type first: pick a chart picture and the fields fill in to suit it (a
 * trend takes the date column, a pie the column with the fewest groups); then adjust what it groups by, the
 * measure and how to aggregate it, with a live preview.
 */
export function ChartBuilder({ profile, initial, startType, onSave, onCancel }: Props) {
  const [first] = useState(() => (initial ? { query: initial.query, x: initial.x, y: initial.y } : draftFor(profile, startType ?? 'column', { query: { agg: 'count' } })))
  const [type, setType] = useState<ChartType>(initial?.type ?? startType ?? 'column')
  const [q, setQ] = useState<Query>(first.query)
  const [x, setX] = useState(first.x)
  const [y, setY] = useState(first.y)
  const [title, setTitle] = useState(initial?.title ?? '')
  const groups = profile.columns.filter(isGroupable)
  const measures = profile.columns.filter(isMeasure)
  const group = q.groupBy !== undefined ? profile.columns[q.groupBy] : undefined
  const one = type === 'kpi'
  const autoTitle = type === 'scatter' && x !== undefined && y !== undefined ? `${profile.columns[y].label} against ${profile.columns[x].label}` : queryTitle(profile, q)
  const spec: ChartSpec = { id: initial?.id ?? 'draft', type, title: title.trim() || autoTitle, reason: initial?.reason ?? 'Built by you.', query: q, x, y, labels: initial?.labels, color: initial?.color }
  const set = (patch: Partial<Query>) => setQ((prev) => ({ ...prev, ...patch }))
  const pick = (t: ChartType) => {
    const d = draftFor(profile, t, { query: q, x, y })
    setType(t)
    setQ(d.query)
    setX(d.x)
    setY(d.y)
  }
  const ready = type === 'scatter' ? x !== undefined && y !== undefined : one || type === 'table' || q.groupBy !== undefined

  return (
    <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
      <div className="flex flex-col gap-3">
        <div role="radiogroup" aria-label="Chart type" className="grid grid-cols-3 gap-1.5">
          {GALLERY.map(({ type: t }) => {
            const why = unavailable(profile, t)
            return (
              <button
                key={t}
                type="button"
                role="radio"
                aria-checked={type === t}
                disabled={why !== null}
                title={why ?? CHART_LABEL[t]}
                onClick={() => pick(t)}
                className={`flex flex-col items-center gap-0.5 rounded-control border-2 px-1 py-1.5 text-micro transition-colors duration-200 ease-soft disabled:cursor-not-allowed disabled:opacity-35 ${
                  type === t ? 'border-ink bg-signal-soft font-semibold' : 'border-line hover:border-ink'
                }`}
              >
                <ChartTypeIcon type={t} className="h-6 w-9" />
                {CHART_LABEL[t]}
              </button>
            )
          })}
        </div>
        {type === 'scatter' ? (
          <>
            <ColumnSelect label="Across (x)" value={x} options={measures} onChange={setX} />
            <ColumnSelect label="Up (y)" value={y} options={measures} onChange={setY} />
          </>
        ) : (
          <>
            {!one && (
              <ColumnSelect
                label={type === 'line' || type === 'area' ? 'Along (usually a date)' : type === 'pie' || type === 'donut' ? 'Slices' : 'Group by'}
                value={q.groupBy}
                options={groups}
                none={type === 'table' ? 'Nothing (every row)' : undefined}
                onChange={(v) => set({ groupBy: v, sort: v !== undefined && profile.columns[v]?.kind === 'period' ? 'time' : 'value-desc', bucket: undefined })}
              />
            )}
            <ColumnSelect label="Measure" value={q.measure} options={measures} none="Rows (count)" onChange={(v) => set({ measure: v, agg: v === undefined ? 'count' : q.agg === 'count' ? 'sum' : q.agg })} />
            {q.measure !== undefined && (
              <Labeled label="Aggregate">
                <Select
                  label="Aggregate"
                  value={q.agg}
                  onChange={(agg) => set({ agg })}
                  options={AGGS.map((a) => ({ value: a, label: AGG_LABEL[a] }))}
                  className="w-full"
                />
              </Labeled>
            )}
            {group?.kind === 'period' && (group.grain === 'day' || group.grain === 'month' || group.grain === 'quarter') && (
              <Labeled label="Group dates by">
                <Select
                  label="Group dates by"
                  value={q.bucket ?? ''}
                  onChange={(bucket) => set({ bucket: (bucket || undefined) as Query['bucket'] })}
                  options={[
                    { value: '', label: group.grain === 'day' ? 'Each date' : group.grain === 'month' ? 'Each month' : 'Each quarter' },
                    ...(group.grain === 'day' ? [{ value: 'month', label: 'Month' }] : []),
                    ...(group.grain !== 'quarter' ? [{ value: 'quarter', label: 'Quarter' }] : []),
                    { value: 'year', label: 'Year' }
                  ]}
                  className="w-full"
                />
              </Labeled>
            )}
            {group && (
              <div className="grid grid-cols-2 gap-2">
                <Labeled label="Sort">
                  <Select
                    label="Sort"
                    value={q.sort ?? (group.kind === 'period' ? 'time' : 'value-desc')}
                    onChange={(sort) => set({ sort: sort as SortBy })}
                    options={[
                      { value: 'value-desc', label: 'Largest first' },
                      { value: 'value-asc', label: 'Smallest first' },
                      { value: 'label', label: 'A to Z' },
                      ...(group.kind === 'period' ? [{ value: 'time', label: 'In time order' }] : [])
                    ]}
                    className="w-full"
                  />
                </Labeled>
                <Labeled label="Show">
                  <Select
                    label="Show"
                    value={q.limit ?? 0}
                    onChange={(limit) => set({ limit: Number(limit) || undefined, other: Number(limit) > 0 })}
                    options={[
                      { value: 0, label: 'All groups' },
                      ...[3, 5, 10, 15, 20].map((n) => ({ value: n, label: `Top ${n} + Other` }))
                    ]}
                    className="w-full"
                  />
                </Labeled>
              </div>
            )}
          </>
        )}
        <Labeled label="Title">
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={autoTitle} className={field} />
        </Labeled>
        <div className="mt-2 flex gap-2">
          <Button onClick={() => onSave(spec)} disabled={!ready}>
            {initial ? 'Save chart' : 'Add to dashboard'}
          </Button>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </div>
      <div className="min-w-0 rounded-panel border-2 border-line p-4">
        <p className="mb-3 text-small font-semibold">{spec.title}</p>
        <ChartView spec={spec} profile={profile} height={260} />
      </div>
    </div>
  )
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-ink-3">{label}</span>
      {children}
    </label>
  )
}

type ColumnOption = { index: number; label: string }
function ColumnSelect({ label, value, options, none, onChange }: { label: string; value?: number; options: ColumnOption[]; none?: string; onChange: (v: number | undefined) => void }) {
  return (
    <Labeled label={label}>
      <Select
        label={label}
        value={value ?? ''}
        onChange={(v) => onChange(v === '' ? undefined : Number(v))}
        options={[
          { value: '', label: none ?? 'Pick a column', disabled: none === undefined },
          ...options.map((c) => ({ value: c.index, label: c.label }))
        ]}
        className="w-full"
      />
    </Labeled>
  )
}
