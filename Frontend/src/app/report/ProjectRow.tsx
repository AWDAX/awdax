import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { timeAgo } from '../../api/dates.ts'
import { createSingleFlight } from '../../api/singleFlight.ts'
import { useInstances } from '../../api/instancesContext.ts'
import { domainOf } from '../../domain/format.ts'
import { DownloadIcon, FileIcon } from '../../ui/appIcons.tsx'
import { PauseIcon, PlayIcon } from '../../ui/icons.tsx'
import { BellToggle } from '../../ui/micro/BellToggle.tsx'
import { FuseButton } from '../../ui/micro/FuseButton.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { setWatched } from '../chat/alerts.ts'
import { deleteLocal } from '../files/localProjects.ts'
import { isUntitled } from '../workspace/groupByDay.ts'
import { STATUS_LABEL } from './reportFilters.ts'
import type { Project, ProjectStatus } from './useProjects.ts'

// Colour carries one meaning each (DESIGN_SYSTEM): yellow = working now, red pen = failed, ink = the rest.
const BADGE: Record<ProjectStatus, string> = {
  running: 'border-ink bg-signal',
  live: 'border-ink',
  paused: 'border-line bg-sunken text-ink-2',
  error: 'border-blocked text-blocked',
  idle: 'border-line text-ink-2',
  uploaded: 'border-line text-ink-2',
  loading: 'border-line text-ink-3',
}

export function StatusBadge({ status }: { status: ProjectStatus }) {
  return <span className={`inline-flex items-center gap-1.5 rounded-control border-2 px-2 py-0.5 text-micro font-medium whitespace-nowrap ${BADGE[status]}`}>{STATUS_LABEL[status]}</span>
}

type Props = {
  p: Project
  watched: boolean
  newRows: number
  onExport: () => void
  onLive: (enabled: boolean) => Promise<void>
}

/** One project in the report: what it is, how it's doing, and what you can do with it. */
export function ProjectRow({ p, watched, newRows, onExport, onLive }: Props) {
  const { remove } = useInstances()
  const { toast } = useToast()
  const flight = useRef(createSingleFlight())
  const [switching, setSwitching] = useState(false)
  // A second click while a pause/resume is pending is ignored.
  const toggleLive = () =>
    void flight.current.run(async () => {
      setSwitching(true)
      try {
        await onLive(!p.liveEnabled)
      } finally {
        setSwitching(false)
      }
    })
  const title = isUntitled(p.title) ? 'Untitled chat' : p.title
  const source = p.kind === 'web' && /^https?:/i.test(p.source) ? domainOf(p.source) : p.source

  return (
    <tr className="border-b border-line align-top hover:bg-sunken/60">
      <td className="max-w-80 py-2.5 pr-3 pl-3">
        <Link to={p.path} className="flex items-start gap-1.5 font-medium hover:underline">
          {p.kind === 'file' && <FileIcon className="mt-1 shrink-0 text-ink-3" aria-label="Uploaded file" />}
          <span className="line-clamp-2">{title}</span>
        </Link>
        {p.status === 'error' && p.detail && <p className="mt-0.5 line-clamp-2 font-mono text-micro text-blocked">{p.detail}</p>}
      </td>
      <td className="py-2.5 pr-3">
        <StatusBadge status={p.status} />
      </td>
      <td className="py-2.5 pr-3 text-right font-mono tabular-nums">
        {p.rows.toLocaleString('en-IN')}
        {p.rowsAddedLastCycle > 0 && <span className="block text-micro text-ink-3">+{p.rowsAddedLastCycle} last cycle</span>}
      </td>
      <td className="max-w-56 truncate py-2.5 pr-3 font-mono text-micro text-ink-2" title={p.source}>
        {source || '—'}
      </td>
      <td className="py-2.5 pr-3 text-right font-mono text-micro text-ink-3 tabular-nums">{p.kind === 'web' ? p.cycle : '—'}</td>
      <td className="py-2.5 pr-3 font-mono text-micro whitespace-nowrap text-ink-3">{timeAgo(p.created_at)}</td>
      <td className="py-2.5 pr-3 font-mono text-micro whitespace-nowrap text-ink-3">{timeAgo(p.updated_at)}</td>
      <td className="py-2 pr-3">
        <div className="flex items-center justify-end gap-1">
          {p.kind === 'web' && (
            <>
              <BellToggle iconOnly size="sm" pressed={watched} count={newRows} onChange={(on) => setWatched(p.id, on, p.rows)} offLabel="Alert me on new rows" onLabel="Alerts on" />
              <button
                type="button"
                aria-label={p.liveEnabled ? `Pause ${title}` : `Resume ${title}`}
                title={p.liveEnabled ? 'Pause tracking' : 'Resume tracking'}
                disabled={switching}
                aria-busy={switching || undefined}
                onClick={toggleLive}
                className="grid size-7 place-items-center rounded-control hover:bg-surface disabled:opacity-50"
              >
                {p.liveEnabled ? <PauseIcon /> : <PlayIcon />}
              </button>
            </>
          )}
          <button type="button" aria-label={`Export ${title}`} title="Export data" disabled={p.rows === 0} onClick={onExport} className="grid size-7 place-items-center rounded-control hover:bg-surface disabled:opacity-30">
            <DownloadIcon />
          </button>
          <FuseButton
            label={`Delete ${title}`}
            iconOnly
            tone="danger"
            size="sm"
            undoWindow={4000}
            onCommit={() =>
              void (p.kind === 'file' ? deleteLocal(p.id) : remove(p.id)).catch(() => toast({ title: 'Couldn’t delete that project', tone: 'error' }))
            }
          />
        </div>
      </td>
    </tr>
  )
}
