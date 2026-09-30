import {
  mapDashboard,
  mapInstanceDetail,
  mapInstanceSummary,
  mapLiveSnapshot,
  type AwdaxpDashboard,
  type AwdaxpInstance,
  type AwdaxpLiveState,
  type AwdaxpMessage,
} from './awdaxpAdapter.ts'
import { request } from './client.ts'
import type {
  DashboardResponse,
  DatasetStats,
  DatasetTable,
  GraphChart,
  GraphParameter,
  InstanceDetail,
  InstanceSummary,
  LiveSnapshot,
  SourcesResponse,
} from './types.ts'

const at = (id: string) => `/api/instances/${encodeURIComponent(id)}`

async function loadInstance(id: string): Promise<InstanceDetail> {
  const [instance, messages] = await Promise.all([
    request<AwdaxpInstance>(at(id)),
    request<AwdaxpMessage[]>(`${at(id)}/messages`),
  ])
  return mapInstanceDetail(instance, messages)
}

/** HTTP client for the AwdaxP backend (proxied in dev — see vite.config.ts). */
export const awdax = {
  health: () => request<{ status: string }>('/health'),

  listInstances: async () => {
    const rows = await request<AwdaxpInstance[]>('/api/instances')
    return rows.map(mapInstanceSummary) as InstanceSummary[]
  },

  createInstance: async (title?: string) => {
    const instance = await request<AwdaxpInstance>('/api/instances', {
      method: 'POST',
      body: JSON.stringify({ title: title?.trim() || 'Untitled chat', goal: '' }),
    })
    return mapInstanceDetail(instance, [])
  },

  getInstance: (id: string) => loadInstance(id),

  deleteInstance: (id: string) => request<void>(at(id), { method: 'DELETE' }),

  updateInstance: async (id: string, patch: { title?: string; archived?: boolean; live_enabled?: boolean }) => {
    const body: Record<string, unknown> = {}
    if (patch.title !== undefined) body.title = patch.title
    if (patch.archived !== undefined) body.archived = patch.archived
    if (patch.live_enabled !== undefined) body.live_enabled = patch.live_enabled
    const instance = await request<AwdaxpInstance>(at(id), { method: 'PATCH', body: JSON.stringify(body) })
    return mapInstanceSummary(instance) as InstanceSummary
  },

  /** Removes all scraped rows for an instance; the chat and messages stay. */
  clearDataset: (id: string) => request<void>(`${at(id)}/dataset`, { method: 'DELETE' }),

  /**
   * Sets the instance goal and starts a research run. AwdaxP clears/replaces dataset work per run;
   * the app sends this once per chat (from New chat), not for follow-ups.
   */
  startTracking: async (id: string, text: string) => {
    await request(`${at(id)}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content: text }),
    })
    return loadInstance(id)
  },

  setLive: async (id: string, enabled: boolean) => {
    await request<AwdaxpLiveState>(`${at(id)}/live`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    })
    return loadInstance(id)
  },

  getDashboard: async (id: string) => {
    const raw = await request<AwdaxpDashboard>(`${at(id)}/dashboard`)
    return mapDashboard(raw) as DashboardResponse
  },

  getLive: async (id: string) => {
    const raw = await request<AwdaxpLiveState>(`${at(id)}/live`)
    return mapLiveSnapshot(raw) as LiveSnapshot
  },

  /** Accepted rows plus the score and provenance of each one. `includePartial` adds rows that were relevant but short of evidence. */
  getDataset: async (id: string, includePartial = false) => {
    const raw = await request<DatasetTable & { records?: DatasetTable['records'] }>(
      `${at(id)}/dataset?limit=5000&include_partial=${includePartial ? 'true' : 'false'}`,
    )
    return {
      columns: raw.columns ?? [],
      rows: raw.rows ?? [],
      row_count: raw.row_count ?? raw.rows?.length ?? 0,
      records: raw.records ?? [],
    } satisfies DatasetTable
  },

  getSources: (id: string) => request<SourcesResponse>(`${at(id)}/sources`),

  getStats: (id: string) => request<DatasetStats>(`${at(id)}/dataset/stats`),

  getGraphParameters: (id: string, includePartial = false) =>
    request<{ parameters: GraphParameter[] }>(`${at(id)}/graph/parameters?include_partial=${includePartial ? 'true' : 'false'}`),

  getGraph: (id: string, parameters: string[], includePartial = false) => {
    const query = new URLSearchParams({ include_partial: includePartial ? 'true' : 'false' })
    if (parameters.length) query.set('parameters', parameters.join(','))
    return request<{ charts: GraphChart[] }>(`${at(id)}/graph?${query}`)
  },

  /** Re-apply scoring after a run. The backend answers 409 while a run is still active. */
  rescore: (id: string) => request<{ accepted: number; partial: number; rejected: number }>(`${at(id)}/dataset/rescore`, { method: 'POST' }),

  streamUrl: (id: string) => `${import.meta.env.VITE_API_BASE_URL ?? ''}${at(id)}/live/stream`,

  /** Same path as the HTTP API, on ws/wss. Vite proxies it in dev; production falls back to the event stream. */
  liveSocketUrl: (id: string) => {
    const path = `${import.meta.env.VITE_API_BASE_URL ?? ''}${at(id)}/live/ws`
    if (/^https?:/i.test(path)) return path.replace(/^http/i, 'ws')
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}${path}`
  },
}
