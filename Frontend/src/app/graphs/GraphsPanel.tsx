import { useEffect, useMemo, useState } from 'react'
import { runQuery } from '../../analytics/aggregate.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { CHART_LABEL, newId } from '../../analytics/spec.ts'
import type { ChartSpec, ChartType } from '../../analytics/spec.ts'
import { queryTitle } from '../../analytics/suggest.ts'
import { Button } from '../../ui/Button.tsx'
import { ChartPicker } from '../dashboard/ChartPicker.tsx'
import { draftFor, GALLERY, unavailable } from '../dashboard/chartTypes.ts'
import { ChartView } from '../dashboard/charts/ChartView.tsx'
import { graphIdeas, graphProfile } from './graphIdeas.ts'
import { Select } from '../../ui/Select.tsx'

type Saved = { instanceId: string; signature: string; overrides: Record<string, ChartSpec>; extra: ChartSpec[] }
const keyFor = (id: string) => `awdax.graphs.v2.${id}`
const signatureOf = (p: TableProfile) => p.columns.map((c) => `${c.name}:${c.kind}${c.virtual ? ':virtual' : ''}`).join('|')

function load(id: string, signature: string): Saved {
  try {
    const saved = JSON.parse(localStorage.getItem(keyFor(id)) || 'null') as Saved | null
    if (saved?.signature === signature && saved.instanceId === id && saved.overrides && Array.isArray(saved.extra)) return saved
  } catch {
    // Storage may be blocked or contain an old layout.
  }
  return { instanceId: id, signature, overrides: {}, extra: [] }
}

function chartTypeReason(profile: TableProfile, chart: ChartSpec, type: ChartType): string | null {
  const reason = unavailable(profile, type)
  if (reason) return reason
  if (type !== 'pie' && type !== 'donut') return null
  const draft = draftFor(profile, type, chart)
  const query = chart.query.agg === 'count' ? { ...draft.query, measure: undefined, agg: 'count' as const } : draft.query
  const values = runQuery(profile, query).rows.map((row) => row.value).filter((value) => value !== null)
  if (values.length < 2 || values.some((value) => value.n < 0n) || !values.some((value) => value.n > 0n)) {
    return 'Needs at least two non-negative groups'
  }
  return null
}

function changeType(profile: TableProfile, chart: ChartSpec, type: ChartType): ChartSpec {
  const draft = draftFor(profile, type, chart)
  const query = chart.query.agg === 'count' && type !== 'scatter'
    ? { ...draft.query, measure: undefined, agg: 'count' as const }
    : draft.query
  const title = type === 'scatter' && draft.x !== undefined && draft.y !== undefined
    ? `${profile.columns[draft.y].label} against ${profile.columns[draft.x].label}` : queryTitle(profile, query)
  return { ...chart, type, query, x: draft.x, y: draft.y, title, reason: `Shown as ${CHART_LABEL[type].toLowerCase()} by your choice.` }
}

/** Automatically picks a useful graph for each available field; all views use the current table rows. */
export function GraphsPanel({ instanceId, profile: raw, includePartial, onIncludePartial }: {
  instanceId: string
  profile: TableProfile
  includePartial?: boolean
  onIncludePartial?: (value: boolean) => void
}) {
  const profile = useMemo(() => graphProfile(raw), [raw])
  const signature = signatureOf(profile)
  const [state, setState] = useState(() => load(instanceId, signature))
  const saved = state.instanceId === instanceId && state.signature === signature ? state : load(instanceId, signature)
  if (saved !== state) setState(saved)
  const [editing, setEditing] = useState<ChartSpec | null>(null)
  const [adding, setAdding] = useState(false)
  const ideas = useMemo(() => graphIdeas(profile), [profile])
  const charts = [...ideas.map((idea) => saved.overrides[idea.id] ?? idea), ...saved.extra]

  useEffect(() => {
    try { localStorage.setItem(keyFor(instanceId), JSON.stringify(saved)) } catch { /* Private browsing can block storage. */ }
  }, [instanceId, saved])

  const update = (chart: ChartSpec) => {
    if (ideas.some((idea) => idea.id === chart.id)) {
      setState({ ...saved, overrides: { ...saved.overrides, [chart.id]: chart } })
    } else {
      setState({ ...saved, extra: saved.extra.map((item) => item.id === chart.id ? chart : item) })
    }
  }

  return (
    <section className="flex flex-col gap-4" aria-label="Graphs from current data">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-[65ch] text-small text-ink-2">
          Charts use the rows in Data. Dates become timelines, categories become comparisons or shares, and each numeric field keeps its own scale.
        </p>
        <div className="flex items-center gap-3">
          {onIncludePartial && <label className="flex items-center gap-2 text-small">
            <input type="checkbox" checked={!!includePartial} onChange={(event) => onIncludePartial(event.target.checked)} />
            Include partial rows
          </label>}
          <Button variant="secondary" onClick={() => setAdding(true)}>Add graph</Button>
        </div>
      </div>
      {charts.length === 0 && (
        <div className="rounded-panel border-2 border-dashed border-line-strong p-5 text-small text-ink-2">
          {profile.rowCount === 0 ? 'Graphs will appear as rows arrive.' : 'These rows have no numeric or repeatable category values to plot. Use Data to inspect the exact text.'}
        </div>
      )}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {charts.map((chart) => {
          const result = runQuery(profile, chart.query)
          return (
            <article key={chart.id} className="min-w-0 rounded-panel border-2 border-ink p-3">
              <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-display font-wide text-h3 font-extrabold">{chart.title}</h3>
                  <p className="mt-1 text-micro text-ink-2">{chart.reason}</p>
                  <p className="mt-1 font-mono text-micro text-ink-3">
                    {result.used.toLocaleString('en-IN')} rows used
                    {result.blank.length ? ` · ${result.blank.length} missing values skipped` : ''}
                    {result.excluded.length ? ` · ${result.excluded.length} invalid values skipped` : ''}
                    {chart.query.limit && result.rows.length > chart.query.limit ? ` · top ${chart.query.limit} groups + Other` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Select
                    label={`Chart type for ${chart.title}`}
                    value={chart.type}
                    onChange={(type) => update(changeType(profile, chart, type))}
                    options={GALLERY.map(({ type }) => ({
                      value: type,
                      label: CHART_LABEL[type],
                      disabled: chartTypeReason(profile, chart, type) !== null,
                    }))}
                  />
                  <Button variant="secondary" onClick={() => setEditing(chart)}>Edit</Button>
                </div>
              </header>
              <ChartView spec={chart} profile={profile} height={270} />
            </article>
          )
        })}
      </div>
      {(editing || adding) && <ChartPicker profile={profile} current={charts} editing={editing ?? undefined}
        onAdd={(chart) => { setState({ ...saved, extra: [...saved.extra, { ...chart, id: newId('g') }] }); setAdding(false) }}
        onUpdate={(chart) => { update(chart); setEditing(null) }}
        onClose={() => { setEditing(null); setAdding(false) }} />}
    </section>
  )
}
