import { useState } from 'react'
import type { DatasetStats, RecordMeta } from '../../api/types.ts'
import { Button } from '../../ui/Button.tsx'

// Re-score hidden: the backend endpoint is a stub that only counts rows (awdax_api/sources_stats_graph.py rescore_dataset).
const SHOW_RESCORE: boolean = false

const TIERS = ['high', 'usable', 'partial', 'low', 'noise', 'unscored'] as const
const PARTS: [string, string][] = [
  ['coverage', 'Concept coverage'],
  ['relevance', 'Subject relevance'],
  ['temporal', 'Temporal fit'],
  ['extraction', 'Extraction'],
  ['completeness', 'Completeness'],
  ['source', 'Source quality'],
]
const VIA: Record<string, string> = {
  exact: 'exact name',
  alias: 'planner alias',
  synonym: 'synonym',
  fuzzy: 'spelling match',
  related: 'related concept',
  value_type: 'value type',
  text: 'mentioned in text',
  learned: 'model-resolved',
  context: 'table caption or heading',
}

function meter(value: number) {
  return (
    <span className="flex h-1.5 w-24 overflow-hidden rounded-sm bg-sunken" aria-hidden>
      <span className="bg-ink" style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </span>
  )
}

/** Tier counts and the mean score. Re-score runs the same rules again after a batch. */
export function ScoreSummary({
  stats,
  includePartial,
  onIncludePartial,
  onRescore,
}: {
  stats: DatasetStats | null
  includePartial?: boolean
  onIncludePartial?: (value: boolean) => void
  onRescore?: () => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const tiers = stats?.tier_counts ?? {}
  return (
    <section aria-label="Scoring" className="flex flex-col gap-3 rounded-panel border-2 border-ink p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">Why rows were kept</h3>
          <p className="max-w-[62ch] text-small text-ink-2">
            Each row is scored on the request, the period and the page. The same rules apply to every source.
            {stats?.mean_score != null ? ` Mean score ${stats.mean_score.toFixed(2)}.` : ''}
            {stats?.inferred_periods ? ` ${stats.inferred_periods.toLocaleString('en-IN')} periods were inferred and stay marked uncertain.` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onIncludePartial && (
            <label className="flex items-center gap-2 text-small">
              <input type="checkbox" checked={!!includePartial} onChange={(event) => onIncludePartial(event.target.checked)} />
              Include partial
            </label>
          )}
          {SHOW_RESCORE && onRescore && (
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => {
                setBusy(true)
                setNote(null)
                void onRescore().then(() => setNote('Re-scored.')).catch((err: unknown) => {
                  setNote(err instanceof Error ? err.message : String(err))
                }).finally(() => setBusy(false))
              }}
            >
              {busy ? 'Re-scoring…' : 'Re-score'}
            </Button>
          )}
        </div>
      </div>
      <ul className="flex flex-wrap gap-2">
        {TIERS.filter((tier) => tiers[tier]).map((tier) => (
          <li key={tier} className="rounded-control border-2 border-ink px-2 py-0.5 font-mono text-micro">
            {tier} {tiers[tier].toLocaleString('en-IN')}
          </li>
        ))}
      </ul>
      {note && <p className="text-small text-ink-2">{note}</p>}
    </section>
  )
}

/** The score, period and source of one accepted row. */
export function RecordDetail({ record }: { record: RecordMeta | null }) {
  if (!record) {
    return <p className="text-small text-ink-3">Pick a row number to see why it was kept. Scores settle when the batch finishes.</p>
  }
  const parts = record.score_breakdown ?? {}
  const matches = Object.entries(record.concept_matches ?? {})
  return (
    <article className="flex flex-col gap-3 rounded-panel border-2 border-line p-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-semibold">
          {record.tier ?? 'unscored'}
          {record.score != null ? <span className="ml-2 font-mono text-small">{record.score.toFixed(2)}</span> : null}
        </h3>
        <p className="font-mono text-micro text-ink-3">
          {record.data_period ?? 'No period'}
          {record.time_inferred ? ' · inferred' : record.data_period ? ' · explicit' : ''}
          {record.time_basis && record.time_basis !== 'none' ? ` · ${record.time_basis.replace(/_/g, ' ')}` : ''}
        </p>
      </header>
      <ul className="flex flex-col gap-1 text-small">
        {PARTS.filter(([key]) => key in parts).map(([key, label]) => (
          <li key={key} className="flex items-center gap-2">
            <span className="w-40 text-ink-2">{label}</span>
            {meter(parts[key])}
            <span className="font-mono text-micro tabular-nums">{parts[key].toFixed(2)}</span>
          </li>
        ))}
        {parts.noise != null && (
          <li className="flex items-center gap-2 text-blocked">
            <span className="w-40">Noise penalty</span>
            {meter(parts.noise)}
            <span className="font-mono text-micro tabular-nums">{parts.noise.toFixed(2)}</span>
          </li>
        )}
      </ul>
      {matches.length > 0 && (
        <ul className="flex flex-col gap-1 font-mono text-micro text-ink-2">
          {matches.map(([concept, match]) => (
            <li key={concept}>
              {concept} ← {match.field} · {VIA[match.via ?? ''] ?? match.via}
              {match.credit != null ? ` · ${Number(match.credit).toFixed(2)}` : ''}
            </li>
          ))}
        </ul>
      )}
      {record.reasons && record.reasons.length > 0 && (
        <ul className="list-disc pl-4 text-small text-ink-2">
          {record.reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      <p className="font-mono text-micro text-ink-3">
        {record.source_domain || record.source_url}
        {record.block_id ? ` · ${record.block_id}` : ''}
        {record.method ? ` · ${record.method}` : ''}
      </p>
    </article>
  )
}
