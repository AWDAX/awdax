import type { DatasetStats, DatasetTable, LiveStatus, ResearchSource, RunEvent, StreamedRows } from './types.ts'

export interface LiveState {
  status: Partial<LiveStatus>
  liveEnabled: boolean
  rowsTotal: number
  dataset: DatasetTable | null
  connected: boolean
  missing: boolean
  events: RunEvent[]
  sources: ResearchSource[]
  stats: DatasetStats | null
  /** Bumps when streamed rows should redraw graphs. */
  graphTick: number
  includePartial: boolean
  partialAdded: number
  refresh: () => void
  setIncludePartial: (value: boolean) => void
}

export const EMPTY_LIVE: LiveState = {
  status: {},
  liveEnabled: false,
  rowsTotal: 0,
  dataset: null,
  connected: false,
  missing: false,
  events: [],
  sources: [],
  stats: null,
  graphTick: 0,
  includePartial: false,
  partialAdded: 0,
  refresh: async () => {},
  setIncludePartial: () => {},
}

/** Keep live source discoveries when an older HTTP snapshot finishes after a stream frame. */
export function mergeSources(current: ResearchSource[], incoming: ResearchSource[]): ResearchSource[] {
  const byUrl = new Map(current.map((source) => [source.url, source]))
  const rank: Record<string, number> = { selected: 0, inspecting: 1, validated: 2, complete: 3, blocked: 3, failed: 3 }
  for (const source of incoming) {
    const before = byUrl.get(source.url)
    if (!before || (rank[source.status] ?? 0) >= (rank[before.status] ?? 0)) byUrl.set(source.url, source)
  }
  return [...byUrl.values()]
}

/** Apply a live patch: sources merge by url, status merges shallowly, `connected` defaults to true. */
export function applyPatch(s: LiveState, patch: Partial<LiveState>): LiveState {
  return {
    ...s,
    ...patch,
    sources: patch.sources ? mergeSources(s.sources, patch.sources) : s.sources,
    status: patch.status ? { ...s.status, ...patch.status } : s.status,
    connected: patch.connected ?? true,
  }
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object'
}

export function asRows(message: Record<string, unknown>): StreamedRows | null {
  if (message.type !== 'rows' || !Array.isArray(message.columns) || !Array.isArray(message.rows)) return null
  const lane = message.lane === 'deep' || message.lane === 'dataset' ? message.lane : 'fast'
  return {
    run_id: String(message.run_id ?? ''),
    lane,
    source_url: String(message.source_url ?? ''),
    columns: message.columns.map(String),
    rows: message.rows as StreamedRows['rows'],
    records: Array.isArray(message.records) ? (message.records as StreamedRows['records']) : [],
    partial_added: Number(message.partial_added ?? 0),
    accepted_total: Number(message.accepted_total ?? 0),
  }
}
