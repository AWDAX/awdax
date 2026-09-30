/**
 * The web app’s view of research data from AwdaxP (awdaxp/). Raw HTTP is mapped in awdaxpAdapter.ts.
 * Dates are ISO strings. Every dataset cell arrives as a string; src/analytics parses them.
 */

export type LivePhase = 'idle' | 'discovery' | 'inspect' | 'extract' | 'merge' | 'sleep' | 'error' | 'stopped'

export interface ChatMessage {
  id: number
  role: 'user' | 'bot'
  /** Markdown: **bold**, _italic_, lists, links. */
  text: string
  created_at: string
}

export interface InstanceSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface InstanceDetail extends InstanceSummary {
  messages: ChatMessage[]
  live_enabled: boolean
  dataset_row_count: number
}

/** ExtractedTable. `name` and `source_url` are missing from the backend's own docs but always sent. */
export interface DatasetTable {
  name?: string
  source_url?: string
  columns: string[]
  rows: (string | number | null)[][]
  row_count?: number
  /** Aligned with `rows` when the dataset endpoint (or a live `rows` frame) sent them. */
  records?: RecordMeta[]
}

export interface LiveStatus {
  phase: LivePhase
  detail: string
  current_source: string
  rows_total: number
  rows_added_last_cycle: number
  cycle: number
  live_enabled: boolean
  updated_at: string
  /** Work budget of one batch, in seconds. */
  batch_seconds?: number
  /** Live tracks start the next batch this long after the previous one started. */
  interval_seconds?: number
  next_cycle_at?: string | null
  /** Which pass last delivered rows: fast read, interactive pass, or a linked dataset. */
  lane?: 'fast' | 'deep' | 'dataset' | null
}

/** One recorded pipeline step (WebSocket `run_event`, or GET …/runs/{id}/events). */
export interface RunEvent {
  id: number
  run_id: string
  phase: string
  detail: string
  created_at: string
}

/** Why a row was kept. Scores are 0–1. The same components apply to every source. */
export interface RecordMeta {
  id: string
  status?: string
  tier?: string
  score?: number
  score_breakdown?: Record<string, number>
  reasons?: string[]
  concept_matches?: Record<string, { field?: string; via?: string; credit?: number }>
  data_period?: string | null
  time_basis?: string
  time_inferred?: boolean
  temporal_confidence?: number
  source_url?: string
  source_domain?: string
  source_title?: string
  method?: string
  extraction_confidence?: number
  block_id?: string
  published_at?: string | null
  fetched_at?: string | null
}

export interface ResearchSource {
  id: string
  url: string
  title: string
  status: string
  accepted: number
  partial: number
  rejected: number
  reason: string
  domain: string
  origin: string
  rank_score?: number | null
  rank_reasons?: string[]
  deep_accepted: number
  deep_notes: string[]
  linked_from?: string | null
}

export interface SourcesResponse {
  candidate_count: number
  sources: ResearchSource[]
  raw_count: number
  partial_count: number
  accepted_count: number
  rejected_count: number
  research_outcome: string
}

export interface DatasetStats {
  row_count: number
  column_count: number
  fill_rate: number
  tier_counts: Record<string, number>
  mean_score: number | null
  inferred_periods: number
  explicit_periods: number
  source_count: number
  period_min: string | null
  period_max: string | null
}

export interface GraphParameter {
  name: string
  unit: string
  points: number
  x_kind: 'period' | 'category'
  period_min: string | null
  period_max: string | null
  series_count: number
}

export interface GraphPoint {
  x: string
  value: number
  raw: string
  observation_id: string
  source_url: string
}

export interface GraphSeries {
  name: string
  points: GraphPoint[]
}

export interface GraphChart {
  parameter: string
  unit: string
  type: 'line' | 'bar'
  x?: string
  group?: string | null
  series: GraphSeries[]
  omitted: number
  duplicates: number
}

/** Accepted rows pushed as a page, the interactive pass, or a linked dataset lands. */
export interface StreamedRows {
  run_id: string
  lane: 'fast' | 'deep' | 'dataset'
  source_url: string
  columns: string[]
  rows: (string | number | null)[][]
  records: RecordMeta[]
  partial_added: number
  accepted_total: number
}

export interface LiveSnapshot {
  live_enabled: boolean
  /** Empty object when the instance has never run. */
  status: Partial<LiveStatus>
  rows_total: number
}

export interface DashboardResponse {
  rows_total: number
  table: DatasetTable | null
  updated_at: string | null
}

/** One server-sent event on /live/stream. The first one after connecting carries the dataset. */
export interface LiveStreamPayload {
  live_enabled: boolean
  status: Partial<LiveStatus>
  rows_total: number
  dataset?: DatasetTable
  /** The bot rewrote a message: refetch the instance. */
  chat_updated?: boolean
}
