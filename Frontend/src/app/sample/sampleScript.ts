import type { ChatMessage, LivePhase } from '../../api/types.ts'
import { SAMPLE_GOAL, sampleReport, sampleTable } from '../../analytics/sampleRun.ts'
import type { LiveState } from '../../api/useLiveStream.ts'

/** One beat of the sample run: what the live stream would say at that moment. */
interface Beat {
  at: number
  phase: LivePhase
  detail: string
  source?: string
}

/** The backend's real phase order and wording (live/cycle.py), with fictional .example pages. */
export const BEATS: Beat[] = [
  { at: 0, phase: 'discovery', detail: 'Searching and validating sources…' },
  { at: 1400, phase: 'discovery', detail: 'Searching and validating sources…', source: 'https://news.example/ev-roundup' },
  { at: 2600, phase: 'discovery', detail: 'Searching and validating sources…', source: 'https://vahan.example/ev/monthly' },
  { at: 3800, phase: 'discovery', detail: 'Searching and validating sources…', source: 'https://autodata.example/india/ev-sales' },
  { at: 5000, phase: 'inspect', detail: 'Inspecting pages and building scrape plan…', source: 'https://vahan.example/ev/monthly' },
  { at: 6400, phase: 'inspect', detail: 'Inspecting pages and building scrape plan…', source: 'https://autodata.example/india/ev-sales' },
  { at: 7800, phase: 'extract', detail: 'Reading the monthly registrations table…', source: 'https://vahan.example/ev/monthly' },
  { at: 9400, phase: 'extract', detail: 'Reading the passenger EV sales table…', source: 'https://autodata.example/india/ev-sales' },
  { at: 10800, phase: 'merge', detail: 'Merging new and changed rows…' },
  { at: 12000, phase: 'sleep', detail: 'Next refresh in 5 minutes' },
]

const at = (ms: number) => new Date(Date.now() - ms).toISOString()

/** The chat as it stands at beat `i`: messages and live state, shaped exactly like the backend's. */
export function stateAt(i: number): { messages: ChatMessage[]; live: LiveState } {
  const beat = BEATS[Math.min(i, BEATS.length - 1)]
  const done = beat.phase === 'sleep'
  const messages: ChatMessage[] = [
    { id: 1, role: 'user', text: SAMPLE_GOAL, created_at: at(13000) },
    done
      ? { id: 2, role: 'bot', text: sampleReport, created_at: at(1000) }
      : { id: 2, role: 'bot', text: '**Live on** — discovery and extraction started.\n\n_Status updates appear above the table; this message fills in when the first pass completes._', created_at: at(12000) },
  ]
  const rows = done ? sampleTable.rows.length : 0
  return {
    messages,
    live: {
      status: { phase: beat.phase, detail: beat.detail, current_source: beat.source ?? '', rows_total: rows, rows_added_last_cycle: rows, cycle: 1, live_enabled: true },
      liveEnabled: true,
      rowsTotal: rows,
      dataset: done ? sampleTable : null,
      connected: true,
      missing: false,
      events: [],
      sources: [],
      stats: null,
      graphTick: 0,
      includePartial: false,
      partialAdded: 0,
      refresh: async () => {},
      setIncludePartial: () => {},
    },
  }
}
