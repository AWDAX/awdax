import { useEffect, useState } from 'react'
import { Link, matchPath, useLocation, useNavigate, useParams } from 'react-router'
import { timeAgo } from '../../api/dates.ts'
import { FileIcon, TrashIcon } from '../../ui/appIcons.tsx'
import { AssistantOrb } from '../../ui/micro/AssistantOrb.tsx'
import { FuseButton } from '../../ui/micro/FuseButton.tsx'
import { deleteLocal, getLocal, onLocalChange } from '../files/localProjects.ts'
import type { LocalProject } from '../files/localProjects.ts'
import { formatBytes } from '../files/readFile.ts'
import { ChatData } from './ChatData.tsx'

/**
 * A chat made from an uploaded file: no scraping, the file's table goes straight into the dashboard and
 * questions. It lives in this browser (IndexedDB), because the backend has nowhere to store uploads.
 */
export default function FilePage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [project, setProject] = useState<LocalProject | null | undefined>(undefined)

  useEffect(() => {
    let alive = true
    getLocal(id)
      .then((p) => alive && setProject(p ?? null))
      .catch(() => alive && setProject(null))
    // Renamed from the sidebar while open: take the new title only, so the table (and the dashboard built
    // on it) stays the same object.
    const off = onLocalChange(() => {
      getLocal(id)
        .then((p) => alive && p && setProject((prev) => (prev && prev.title !== p.title ? { ...prev, title: p.title } : prev)))
        .catch(() => undefined)
    })
    return () => {
      alive = false
      off()
    }
  }, [id])

  if (project === undefined) return <p className="p-8 font-mono text-micro text-ink-3">Opening the file…</p>
  if (project === null) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-h2 font-extrabold">This upload isn’t in this browser.</h1>
        <p className="mt-3 text-ink-2">Uploaded files stay on the device they were added on, and this one may have been deleted.</p>
        <Link to="/app" className="mt-6 inline-block underline underline-offset-2">
          Start a new chat
        </Link>
      </div>
    )
  }

  const t = project.table
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-6">
      <header className="flex flex-wrap items-start gap-3 border-b-2 border-ink pb-4">
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-h3 font-extrabold break-words">{project.title}</h1>
          <p className="mt-1 font-mono text-micro text-ink-3">
            Uploaded {timeAgo(project.created_at)} · kept in this browser only
          </p>
        </div>
        <FuseButton
          label="Delete"
          undoLabel="Undo"
          doneLabel="Deleted"
          tone="danger"
          icon={<TrashIcon />}
          onCommit={async () => {
            // The fuse can commit after the page was left (the user opened another chat): only leave if still here.
            if (matchPath(pathname, window.location.pathname)) navigate('/app', { replace: true })
            await deleteLocal(project.id)
          }}
        />
      </header>

      <div className="flex max-w-3xl gap-3">
        <AssistantOrb size="md" className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-body">
            <span className="inline-flex items-center gap-1.5 rounded-control border-2 border-line bg-sunken px-2 py-0.5 text-small">
              <FileIcon /> {project.fileName} · {formatBytes(project.fileSize)}
            </span>
            Read {t.rows.length.toLocaleString('en-IN')} rows and {t.columns.length} columns.
          </p>
          {project.note && <p className="mt-1 text-small text-ink-2">{project.note}</p>}
          <p className="mt-1 text-small text-ink-2">
            Every cell was kept exactly as written; numbers, dates and currencies are read for the charts, and anything that couldn’t be read is listed under each chart.
          </p>
        </div>
      </div>

      <ChatData instanceId={`file-${project.id}`} table={t} title={project.title} />
    </div>
  )
}
