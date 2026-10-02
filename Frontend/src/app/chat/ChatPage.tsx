import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, matchPath, useLocation, useNavigate, useParams } from 'react-router'
import { awdax } from '../../api/awdax.ts'
import { ApiError } from '../../api/client.ts'
import { timeAgo } from '../../api/dates.ts'
import { useInstances } from '../../api/instancesContext.ts'
import type { InstanceDetail } from '../../api/types.ts'
import { useLiveStream } from '../../api/useLiveStream.ts'
import { createSingleFlight } from '../../api/singleFlight.ts'
import { Button } from '../../ui/Button.tsx'
import { useToast } from '../../ui/toast/toastContext.ts'
import { useVisits } from '../sources/useVisits.ts'
import { isUntitled } from '../workspace/groupByDay.ts'
import { markSeen, notify, setWatched, useAlerts } from './alerts.ts'
import { ChatMenu } from './ChatMenu.tsx'
import { ChatView } from './ChatView.tsx'

/**
 * One web request, wired to the backend: the instance and its messages, the live stream, the pages read,
 * pause/resume, delete and row alerts. What it draws is ChatView (shared with the sample run).
 */
export default function ChatPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { remove, upsert, list, loading: listLoading, listOk } = useInstances()
  const { toast } = useToast()
  const [chat, setChat] = useState<InstanceDetail | null>(null)
  const [missing, setMissing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [override, setOverride] = useState<boolean | null>(null)
  const alerts = useAlerts()
  const watched = alerts[id]?.watched ?? false
  const lastRows = useRef<number | null>(null)
  const { visits, record } = useVisits(id)
  const refetch = useCallback(async () => {
    try {
      const detail = await awdax.getInstance(id)
      setChat(detail)
      setLoadError(null)
      upsert(detail)
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMissing(true)
      else setLoadError(err instanceof Error ? err.message : String(err))
    }
  }, [id, upsert])

  useEffect(() => {
    const t = window.setTimeout(refetch, 0)
    return () => window.clearTimeout(t)
  }, [refetch])

  const gone = missing || (!listLoading && listOk && !!id && !list.some((instance) => instance.id === id))
  // A chat known to be gone is not streamed: pass no id so no socket or dataset request is made for it.
  const live = useLiveStream(gone ? null : id, {
    onChatUpdated: refetch,
    onPayload: (p) => {
      setOverride(null)
      record(p.status?.current_source, p.status?.phase)
      const before = lastRows.current
      lastRows.current = p.rows_total
      if (before !== null && p.rows_total > before && watched) {
        const n = p.rows_total - before
        const title = `${n.toLocaleString('en-IN')} new ${n === 1 ? 'row' : 'rows'}`
        toast({ title, description: chat?.title, tone: 'success' })
        notify(`AWDAX: ${title}`, chat?.title ?? '')
      }
    },
  })
  const liveEnabled = override ?? live.liveEnabled
  const view = { ...live, liveEnabled, status: override === false ? { ...live.status, phase: 'stopped' as const } : live.status }

  useEffect(() => {
    if (live.rowsTotal > 0) markSeen(id, live.rowsTotal)
  }, [id, live.rowsTotal])

  const flight = useRef(createSingleFlight())
  const [switching, setSwitching] = useState(false)
  const setLive = async (enabled: boolean) => {
    // A second click while a pause/resume is pending is ignored.
    await flight.current.run(async () => {
      setSwitching(true)
      try {
        const snapshot = await awdax.setLive(id, enabled)
        setOverride(snapshot.live_enabled)
      } catch (err) {
        toast({ title: enabled ? 'Couldn’t resume' : 'Couldn’t pause', description: err instanceof Error ? err.message : String(err), tone: 'error' })
      } finally {
        setSwitching(false)
      }
    })
  }

  if (gone || live.missing) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display font-wide text-h2 font-extrabold">This chat no longer exists.</h1>
        <p className="mt-3 text-ink-2">It may have been deleted in another tab.</p>
        <Link to="/app" className="mt-6 inline-block underline underline-offset-2">
          Start a new chat
        </Link>
      </div>
    )
  }

  // The chat never loaded (server down or not connected): say why instead of waiting on "Loading…" forever.
  if (!chat && loadError) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display font-wide text-h2 font-extrabold">This chat can’t load right now.</h1>
        <p className="mt-3 max-w-[60ch] text-ink-2">{loadError}</p>
        <div className="mt-6 flex gap-2">
          <Button onClick={() => void refetch()}>Try again</Button>
          <Link to="/app" className="inline-flex h-10 items-center px-3 text-small underline underline-offset-2">
            Back to New chat
          </Link>
        </div>
      </div>
    )
  }

  const raw = chat?.title
  const title = raw && !isUntitled(raw) ? raw : 'Untitled chat'
  const actions = (
    <ChatMenu
      watched={watched}
      onWatch={(on) => setWatched(id, on, live.rowsTotal)}
      liveEnabled={liveEnabled}
      switching={switching}
      onLive={(enabled) => void setLive(enabled)}
      onDelete={async () => {
        if (matchPath(pathname, window.location.pathname)) navigate('/app', { replace: true })
        await remove(id).catch(() => toast({ title: 'Couldn’t delete that chat', tone: 'error' }))
      }}
    />
  )

  return (
    <ChatView
      instanceKey={id}
      title={title}
      meta={`${chat ? `Started ${timeAgo(chat.created_at)} · updated ${timeAgo(chat.updated_at)}` : 'Loading…'} · ${liveEnabled ? 'live' : 'paused'}`}
      messages={chat?.messages ?? []}
      live={view}
      visits={visits}
      actions={actions}
      onRetry={async () => {
        await setLive(false)
        await setLive(true)
      }}
    />
  )
}
