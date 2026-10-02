/**
 * Maps AwdaxP (/api on port 8000) responses onto the frontend contract in types.ts.
 * The React app was written against an older backend shape; AwdaxP is the live server now.
 */
import type {
  ChatMessage,
  DashboardResponse,
  InstanceDetail,
  InstanceSummary,
  LivePhase,
  LiveSnapshot,
  LiveStatus,
} from './types.ts'

/** Raw instance row from GET /api/instances and GET /api/instances/:id */
export interface AwdaxpInstance {
  id: string
  title: string
  goal?: string
  archived?: boolean
  live_enabled: boolean
  created_at: string
  updated_at: string
  /** Present on the single-instance response only; the list omits it. */
  dataset_row_count?: number
}

export interface AwdaxpMessage {
  id: string
  instance_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export interface AwdaxpRun {
  id: string
  instance_id: string
  status: string
  phase: string
  detail?: string
  rows_total?: number
  rows_added?: number
  updated_at?: string
}

/** GET /api/instances/:id/live and SSE `status` events */
export interface AwdaxpLiveState {
  enabled: boolean
  latest_run: AwdaxpRun | null
  interval_seconds?: number
  batch_seconds?: number
  next_cycle_at?: string | null
  rows_total: number
}

export interface AwdaxpDashboard {
  instance: AwdaxpInstance
  rows_total: number
  table: {
    columns: string[]
    rows: (string | number | null)[][]
    row_count?: number
  } | null
}

export const PHASE: Record<string, LivePhase> = {
  queued: 'idle',
  planning: 'discovery',
  discovery: 'discovery',
  rendering: 'inspect',
  extracting: 'extract',
  scraping: 'extract',
  // Live mode between refreshes ("next check in…"), same as a finished cycle.
  live: 'sleep',
  scoring: 'extract',
  merging: 'merge',
  complete: 'sleep',
  failed: 'error',
  cancelled: 'stopped',
}

function messageKey(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (Math.imul(31, h) + id.charCodeAt(i)) | 0
  return Math.abs(h) || 1
}

function mapMessage(row: AwdaxpMessage): ChatMessage {
  return {
    id: messageKey(row.id),
    role: row.role === 'user' ? 'user' : 'bot',
    text: row.content,
    created_at: row.created_at,
  }
}

function currentSource(detail: string | undefined): string {
  if (!detail) return ''
  const rendering = detail.match(/Rendering\s+(\S+)/i)
  if (rendering) return rendering[1]
  const host = detail.match(/^([^:]+):/)
  if (host) return host[1].trim()
  return ''
}

function livePhase(run: AwdaxpRun | null | undefined, liveEnabled: boolean): LivePhase {
  if (!liveEnabled) return 'stopped'
  if (!run) return 'idle'
  if (run.status === 'failed') return 'error'
  if (run.status === 'cancelled') return 'stopped'
  if (run.status === 'succeeded' && run.phase === 'complete') return liveEnabled ? 'sleep' : 'idle'
  return PHASE[run.phase] ?? 'idle'
}

export function mapLiveStatus(state: AwdaxpLiveState): Partial<LiveStatus> {
  const run = state.latest_run
  const phase = livePhase(run, state.enabled)
  return {
    phase,
    detail: run?.detail ?? '',
    current_source: currentSource(run?.detail),
    rows_total: state.rows_total,
    rows_added_last_cycle: run?.rows_added ?? 0,
    live_enabled: state.enabled,
    updated_at: run?.updated_at ?? '',
    batch_seconds: state.batch_seconds,
    interval_seconds: state.interval_seconds,
    next_cycle_at: state.next_cycle_at,
  }
}

export function mapLiveSnapshot(state: AwdaxpLiveState): LiveSnapshot {
  return {
    live_enabled: state.enabled,
    status: mapLiveStatus(state),
    rows_total: state.rows_total,
  }
}

export function mapInstanceSummary(row: AwdaxpInstance): InstanceSummary {
  return {
    id: row.id,
    title: row.title,
    created_at: row.created_at,
    updated_at: row.updated_at,
  }
}

export function mapInstanceDetail(row: AwdaxpInstance, messages: AwdaxpMessage[]): InstanceDetail {
  return {
    ...mapInstanceSummary(row),
    messages: messages.map(mapMessage),
    live_enabled: row.live_enabled,
    dataset_row_count: row.dataset_row_count ?? 0,
  }
}

export function mapDashboard(raw: AwdaxpDashboard): DashboardResponse {
  return {
    rows_total: raw.rows_total,
    table: raw.table,
    updated_at: raw.instance.updated_at,
  }
}
