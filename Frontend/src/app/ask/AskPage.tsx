import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import type { DatasetTable } from '../../api/types.ts'
import { FileIcon, SearchIcon } from '../../ui/appIcons.tsx'
import { loadTable } from '../report/loadTable.ts'
import { useProjects } from '../report/useProjects.ts'
import { isUntitled } from '../workspace/groupByDay.ts'
import { PageHeader } from '../workspace/PageHeader.tsx'
import { ProjectAsk } from './ProjectAsk.tsx'

/**
 * Ask database: pick any project that has rows (a web request or an uploaded file) and question it, in words,
 * with suggested questions, or with the query builder. Answers are shared with that project's chat.
 */
export default function AskPage() {
  const { projects, loading } = useProjects()
  const [params, setParams] = useSearchParams()
  const [filter, setFilter] = useState('')
  const [table, setTable] = useState<{ key: string; table: DatasetTable | null; error?: string } | null>(null)
  const withData = useMemo(() => projects.filter((p) => p.rows > 0), [projects])
  const picked = params.get('p') ?? ''
  const current = withData.find((p) => `${p.kind}:${p.id}` === picked) ?? withData[0]
  const currentKey = current ? `${current.kind}:${current.id}` : ''
  const shown = filter ? withData.filter((p) => p.title.toLowerCase().includes(filter.toLowerCase())) : withData

  const kind = current?.kind
  const pid = current?.id
  useEffect(() => {
    if (!kind || !pid) return
    let alive = true
    loadTable(kind, pid)
      .then((t) => alive && setTable({ key: `${kind}:${pid}`, table: t }))
      .catch((err) => alive && setTable({ key: `${kind}:${pid}`, table: null, error: err instanceof Error ? err.message : String(err) }))
    return () => {
      alive = false
    }
  }, [kind, pid])

  const ready = table && table.key === currentKey ? table : null

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-5 px-5 py-6">
      <PageHeader eyebrow="Workspace" title="Ask database" />
      {withData.length === 0 ? (
        <p className="rounded-panel border-2 border-dashed border-line-strong p-8 text-center text-ink-2">
          {loading ? 'Loading projects…' : 'No project has rows yet. Start a web request or upload a file from '}
          {!loading && (
            <Link to="/app" className="underline underline-offset-2">
              New chat
            </Link>
          )}
          {!loading && '.'}
        </p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <aside className="flex flex-col gap-2">
            <label className="flex h-9 items-center gap-2 rounded-control border-2 border-line px-2.5 focus-within:border-ink">
              <SearchIcon className="shrink-0 text-ink-3" />
              <span className="sr-only">Find a project</span>
              <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Find a project" className="w-full min-w-0 bg-transparent text-small outline-none" />
            </label>
            <ul className="flex max-h-[60vh] flex-col gap-1 overflow-y-auto" data-lenis-prevent>
              {shown.map((p) => {
                const key = `${p.kind}:${p.id}`
                const on = key === currentKey
                return (
                  <li key={key}>
                    <button
                      type="button"
                      aria-current={on || undefined}
                      onClick={() => setParams({ p: key })}
                      className={`flex w-full flex-col rounded-control border-2 px-2.5 py-2 text-left ${on ? 'border-ink bg-signal-soft' : 'border-transparent hover:bg-sunken'}`}
                    >
                      <span className="flex items-center gap-1.5 text-small font-medium">
                        {p.kind === 'file' && <FileIcon className="shrink-0 text-ink-3" />}
                        <span className="truncate">{isUntitled(p.title) ? 'Untitled chat' : p.title}</span>
                      </span>
                      <span className="font-mono text-micro text-ink-3">{p.rows.toLocaleString('en-IN')} rows</span>
                    </button>
                  </li>
                )
              })}
            </ul>
          </aside>
          <section className="min-w-0">
            {!ready && <p className="font-mono text-micro text-ink-3">Loading the table…</p>}
            {ready?.error && <p className="text-blocked">{ready.error}</p>}
            {ready?.table && current && (
              <ProjectAsk
                key={currentKey}
                table={ready.table}
                title={isUntitled(current.title) ? 'Untitled chat' : current.title}
                instanceKey={current.kind === 'file' ? `file-${current.id}` : current.id}
                path={current.path}
              />
            )}
          </section>
        </div>
      )}
    </div>
  )
}
