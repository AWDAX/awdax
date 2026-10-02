import { mapLiveSnapshot } from '../../api/awdaxpAdapter.ts'
import type { AwdaxpLiveState } from '../../api/awdaxpAdapter.ts'
import { EMPTY_LIVE, mergeSources } from '../../api/liveState.ts'
import type { LiveState } from '../../api/liveState.ts'
import type { ChatMessage, DatasetStats, DatasetTable, ResearchSource, RunEvent } from '../../api/types.ts'
import type { Visit } from '../sources/buildSources.ts'

/** One recorded moment of a real run, `t` ms after it started. */
export type Step =
  | { t: number; kind: 'status'; state: AwdaxpLiveState }
  | { t: number; kind: 'event'; event: RunEvent }
  | { t: number; kind: 'source'; source: ResearchSource }
  | { t: number; kind: 'message'; message: ChatMessage }
  | { t: number; kind: 'done' }

/** A real run, recorded by scripts/record-demo.mjs and trimmed by scripts/build-replay.mjs into public/demo/. */
export interface Recording {
  slug: string
  prompt: string
  title: string
  recordedAt: string
  durationMs: number
  steps: Step[]
  final: { dataset: DatasetTable; sources: ResearchSource[]; stats: DatasetStats | null }
}

/** A replay plays the whole run in about this long, whatever the real run took. */
export const REPLAY_MS = 25_000
const MIN_GAP = 120
const MAX_GAP = 2_500

/** When each step shows: the real gaps scaled down to fit REPLAY_MS, each clamped so nothing flashes or stalls. */
export function schedule(rec: Recording): number[] {
  const scale = REPLAY_MS / Math.max(rec.durationMs, 1)
  const out: number[] = []
  let prev = rec.steps[0]?.t ?? 0
  let at = 0
  for (const [i, step] of rec.steps.entries()) {
    if (i > 0) at += Math.min(MAX_GAP, Math.max(MIN_GAP, (step.t - prev) * scale))
    prev = step.t
    out.push(Math.round(at))
  }
  return out
}

/**
 * The chat as it stood after step `i`, built the way the live page builds it: status through the app's own
 * adapter, sources through mergeSources, the last 12 run events. Rows arrive with the run's final table.
 */
export function replayAt(rec: Recording, i: number): { messages: ChatMessage[]; live: LiveState; visits: Visit[] } {
  // A new run is live from the start: before its first status it reads "Waiting to start", not "Tracking paused".
  let live: LiveState = { ...EMPTY_LIVE, connected: true, liveEnabled: true }
  const messages: ChatMessage[] = []
  const visits: Visit[] = []
  for (const step of rec.steps.slice(0, Math.max(0, i) + 1)) {
    if (step.kind === 'status') {
      const snap = mapLiveSnapshot(step.state)
      live = { ...live, status: snap.status, liveEnabled: snap.live_enabled, rowsTotal: snap.rows_total }
      const source = snap.status.current_source
      if (source && visits.at(-1)?.source !== source) visits.push({ source, phase: snap.status.phase, at: rec.recordedAt })
    } else if (step.kind === 'event') {
      live = { ...live, events: [...live.events.filter((e) => e.id !== step.event.id), step.event].slice(-12) }
    } else if (step.kind === 'source') {
      live = { ...live, sources: mergeSources(live.sources, [step.source]) }
    } else if (step.kind === 'message') {
      messages.push(step.message)
    } else {
      const { dataset, sources, stats } = rec.final
      live = {
        ...live,
        dataset: dataset.rows.length ? dataset : null,
        rowsTotal: dataset.row_count ?? dataset.rows.length,
        sources: mergeSources(live.sources, sources),
        stats,
        graphTick: 1,
      }
    }
  }
  return { messages, live, visits }
}
