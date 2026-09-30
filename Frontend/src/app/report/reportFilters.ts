import { apiDate, apiTime } from '../../api/dates.ts'
import type { Project, ProjectStatus } from './useProjects.ts'

export type FilterKey = 'all' | 'running' | 'live' | 'paused' | 'error' | 'data' | 'empty' | 'uploaded'
export type QueryKey = 'most-rows' | 'today' | 'failed' | 'never-ran' | 'new-rows'
export type SortKey = 'updated' | 'created' | 'rows' | 'title'

export const FILTERS: { key: FilterKey; label: string; test: (p: Project) => boolean }[] = [
  { key: 'all', label: 'All', test: () => true },
  { key: 'running', label: 'Running', test: (p) => p.status === 'running' },
  { key: 'live', label: 'Live', test: (p) => p.kind === 'web' && p.liveEnabled && p.status !== 'error' },
  { key: 'paused', label: 'Paused', test: (p) => p.status === 'paused' },
  { key: 'error', label: 'Error', test: (p) => p.status === 'error' },
  { key: 'data', label: 'Has data', test: (p) => p.rows > 0 },
  { key: 'empty', label: 'Empty', test: (p) => p.rows === 0 },
  { key: 'uploaded', label: 'Uploaded files', test: (p) => p.kind === 'file' },
]

const startOfToday = () => {
  const d = new Date()
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** One-click questions about the projects themselves. Each sets a filter and a sort. */
export const QUERIES: { key: QueryKey; label: string; test: (p: Project) => boolean; sort?: SortKey }[] = [
  { key: 'most-rows', label: 'Most rows', test: (p) => p.rows > 0, sort: 'rows' },
  { key: 'today', label: 'Updated today', test: (p) => (apiDate(p.updated_at)?.getTime() ?? 0) >= startOfToday(), sort: 'updated' },
  { key: 'new-rows', label: 'New rows last cycle', test: (p) => p.rowsAddedLastCycle > 0, sort: 'rows' },
  { key: 'failed', label: 'Failed', test: (p) => p.status === 'error', sort: 'updated' },
  { key: 'never-ran', label: 'Never ran', test: (p) => p.kind === 'web' && p.status === 'idle' && p.cycle === 0 && p.rows === 0 },
]

export function applyReport(projects: Project[], opts: { search: string; filter: FilterKey; query: QueryKey | null; sort: SortKey }) {
  const q = opts.search.trim().toLowerCase()
  const f = FILTERS.find((x) => x.key === opts.filter)!
  const query = QUERIES.find((x) => x.key === opts.query)
  const sort = query?.sort ?? opts.sort
  const out = projects.filter(
    (p) => f.test(p) && (!query || query.test(p)) && (!q || p.title.toLowerCase().includes(q) || p.source.toLowerCase().includes(q) || p.detail.toLowerCase().includes(q)),
  )
  const by: Record<SortKey, (a: Project, b: Project) => number> = {
    updated: (a, b) => apiTime(b.updated_at) - apiTime(a.updated_at),
    created: (a, b) => apiTime(b.created_at) - apiTime(a.created_at),
    rows: (a, b) => b.rows - a.rows,
    title: (a, b) => a.title.localeCompare(b.title),
  }
  return out.sort(by[sort])
}

export const STATUS_LABEL: Record<ProjectStatus, string> = {
  running: 'Running',
  live: 'Live · up to date',
  paused: 'Paused',
  error: 'Error',
  idle: 'Idle',
  uploaded: 'Uploaded file',
  loading: 'Checking…',
}
