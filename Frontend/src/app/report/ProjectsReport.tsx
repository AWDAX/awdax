import { useMemo, useState } from 'react'
import { profileTable } from '../../analytics/profile.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { SearchIcon } from '../../ui/appIcons.tsx'
import { Select } from '../../ui/Select.tsx'
import type { SelectOption } from '../../ui/Select.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { TutorialTrigger } from '../../ui/tutorial/TutorialTrigger.tsx'
import { useAlerts } from '../chat/alerts.ts'
import { ExportDialog } from '../export/ExportDialog.tsx'
import { PageHeader } from '../workspace/PageHeader.tsx'
import { loadTable, setLiveAndSnapshot } from './loadTable.ts'
import { ProjectRow } from './ProjectRow.tsx'
import { applyReport, FILTERS, QUERIES } from './reportFilters.ts'
import type { FilterKey, QueryKey, SortKey } from './reportFilters.ts'
import { useProjects } from './useProjects.ts'
import type { Project } from './useProjects.ts'

const SORTS: SelectOption<SortKey>[] = [
  { value: 'updated', label: 'Last updated' },
  { value: 'created', label: 'Newest first' },
  { value: 'rows', label: 'Most rows' },
  { value: 'title', label: 'Title A to Z' },
]

const chip = (on: boolean) =>
  `rounded-control border-2 px-2.5 py-1 text-small transition-colors duration-300 ease-soft ${on ? 'border-ink bg-ink text-on-ink' : 'border-line hover:border-ink'}`

/**
 * Every project in one report: what was searched and scraped, how many rows each holds and what it's doing
 * now, with search, filter buttons, one-click queries and row actions. Web statuses refresh every 15 s.
 */
export default function ProjectsReport() {
  const { projects, loading, setSnap } = useProjects()
  const alerts = useAlerts()
  const { toast } = useToast()
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<FilterKey>('all')
  const [query, setQuery] = useState<QueryKey | null>(null)
  const [sort, setSort] = useState<SortKey>('updated')
  const [exporting, setExporting] = useState<{ p: Project; profile: TableProfile } | null>(null)

  const rows = useMemo(() => applyReport(projects, { search, filter, query, sort }), [projects, search, filter, query, sort])
  const kpis = [
    { label: 'Projects', value: projects.length },
    { label: 'Running now', value: projects.filter((p) => p.status === 'running').length },
    { label: 'Live tracking', value: projects.filter((p) => p.kind === 'web' && p.liveEnabled).length },
    { label: 'Rows collected', value: projects.reduce((n, p) => n + p.rows, 0) },
    { label: 'Errors', value: projects.filter((p) => p.status === 'error').length },
    { label: 'Uploaded files', value: projects.filter((p) => p.kind === 'file').length },
  ]

  const exportProject = async (p: Project) => {
    try {
      const table = await loadTable(p.kind, p.id)
      if (!table || table.rows.length === 0) throw new Error('This project has no rows yet.')
      setExporting({ p, profile: profileTable(table) })
    } catch (err) {
      toast({ title: 'Couldn’t load that project', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    }
  }
  const setLive = async (p: Project, enabled: boolean) => {
    try {
      setSnap(p.id, await setLiveAndSnapshot(p.id, enabled))
    } catch (err) {
      toast({ title: enabled ? 'Couldn’t resume' : 'Couldn’t pause', description: err instanceof Error ? err.message : String(err), tone: 'error' })
    }
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader eyebrow="Workspace" title="Projects report" />
        <TutorialTrigger label="Watch tutorial" variant="secondary" />
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {kpis.map((k) => (
          <div key={k.label} className="rounded-panel border-2 border-ink p-3">
            <dt className="text-micro text-ink-3">{k.label}</dt>
            <dd className="mt-1 font-display font-wide text-h3 font-extrabold tabular-nums">{k.value.toLocaleString('en-IN')}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex h-10 w-full items-center gap-2 rounded-control border-2 border-line px-3 focus-within:border-ink sm:w-80">
            <SearchIcon className="shrink-0 text-ink-3" />
            <span className="sr-only">Search projects</span>
            <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search titles, sources, errors" className="w-full min-w-0 bg-transparent text-small outline-none placeholder:text-ink-3" />
          </label>
          <div className="ml-auto flex items-center gap-2 text-small">
            <span aria-hidden className="text-ink-3">Sort</span>
            <Select label="Sort projects" value={sort} options={SORTS} onChange={setSort} className="w-44" />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" aria-pressed={filter === f.key} onClick={() => setFilter(f.key)} className={chip(filter === f.key)}>
              {f.label} <span className="font-mono text-micro opacity-70">{projects.filter(f.test).length}</span>
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Quick queries">
          <span className="mr-1 font-mono text-micro text-ink-3">Quick queries</span>
          {QUERIES.map((q) => (
            <button key={q.key} type="button" aria-pressed={query === q.key} onClick={() => setQuery(query === q.key ? null : q.key)} className={chip(query === q.key)}>
              {q.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-panel border-2 border-ink" data-lenis-prevent>
        <table className="w-full min-w-[56rem] text-small">
          <thead>
            <tr className="border-b-2 border-ink text-left">
              <th className="py-2 pr-3 pl-3 font-medium">Project</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 text-right font-medium">Rows</th>
              <th className="py-2 pr-3 font-medium">Source now</th>
              <th className="py-2 pr-3 text-right font-medium">Cycle</th>
              <th className="py-2 pr-3 font-medium">Started</th>
              <th className="py-2 pr-3 font-medium">Updated</th>
              <th className="py-2 pr-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const a = alerts[p.id]
              return (
                <ProjectRow
                  key={`${p.kind}-${p.id}`}
                  p={p}
                  watched={a?.watched ?? false}
                  newRows={a?.watched ? Math.max(0, p.rows - a.seen) : 0}
                  onExport={() => void exportProject(p)}
                  onLive={(on) => setLive(p, on)}
                />
              )
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <p className="p-8 text-center text-small text-ink-3">{loading ? 'Loading projects…' : projects.length ? 'No projects match these filters.' : 'No projects yet. Start one from New chat.'}</p>
        )}
      </div>

      {exporting && (
        <ExportDialog profile={exporting.profile} scope={{ kind: 'rows', filters: [], label: 'All rows' }} title={exporting.p.title} onClose={() => setExporting(null)} />
      )}
    </div>
  )
}

