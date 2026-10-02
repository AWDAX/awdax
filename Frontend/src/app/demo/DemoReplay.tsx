import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { timeAgo } from '../../api/dates.ts'
import { Button } from '../../ui/Button.tsx'
import { PlayIcon, ReplayIcon } from '../../ui/icons.tsx'
import { ChatView } from '../chat/ChatView.tsx'
import { replayAt, schedule } from './replay.ts'
import type { Recording } from './replay.ts'

/**
 * A real AWDAX run, recorded once and replayed in about REPLAY_MS: the same ChatView the live page uses, fed the
 * run's own frames, rows and sources (public/demo/<slug>.json). No "recorded" badge (owner's call, 3 Oct 2026), but
 * the times stay the run's real ones, never faked to "just now". Nothing is sent to the backend. "Run it live"
 * opens New chat with the same prompt for a new run.
 */
export default function DemoReplay() {
  const { slug = '' } = useParams()
  const navigate = useNavigate()
  // The card's prompt, so a replay that can't load still offers the genuine run.
  const handed = (useLocation().state as { prompt?: string } | null)?.prompt
  const [rec, setRec] = useState<Recording | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [step, setStep] = useState(0)
  const [run, setRun] = useState(0)

  useEffect(() => {
    let off = false
    fetch(`/demo/${encodeURIComponent(slug)}.json`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((json: Recording) => !off && setRec(json))
      .catch(() => !off && setError('This run isn’t available right now.'))
    return () => {
      off = true
    }
  }, [slug])

  const at = useMemo(() => (rec ? schedule(rec) : []), [rec])
  useEffect(() => {
    if (!rec || step >= at.length - 1) return
    const t = window.setTimeout(() => setStep((s) => s + 1), at[step + 1] - at[step])
    return () => window.clearTimeout(t)
  }, [rec, at, step, run])

  const state = useMemo(() => (rec ? replayAt(rec, step) : null), [rec, step])

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-5 py-16">
        <h1 className="font-display text-h2 font-extrabold">{error}</h1>
        {handed && <p className="mt-3 text-ink-2">You can still start “{handed}” as a new run; it takes several minutes.</p>}
        <div className="mt-6 flex flex-wrap items-center gap-3">
          {handed && (
            <Button onClick={() => navigate('/app', { state: { prompt: handed } })}>
              <PlayIcon /> Run it live
            </Button>
          )}
          <Link to="/app" className="inline-flex h-10 items-center px-1 text-small underline underline-offset-2">
            Back to New chat
          </Link>
        </div>
      </div>
    )
  }
  if (!rec || !state) return <p className="px-5 py-16 text-center text-ink-2">Loading…</p>

  const finished = step >= at.length - 1
  const rows = state.live.rowsTotal
  return (
    <ChatView
      instanceKey={`demo-${rec.slug}`}
      offline
      title={rec.title}
      meta={`Started ${timeAgo(rec.recordedAt)}${finished ? ` · ${rows.toLocaleString('en-IN')} ${rows === 1 ? 'row' : 'rows'}` : ''}`}
      messages={state.messages}
      live={state.live}
      visits={state.visits}
      runElapsedSec={(rec.steps[Math.min(step, rec.steps.length - 1)]?.t ?? 0) / 1000}
      onRetry={() => undefined}
      actions={
        <>
          {!finished && (
            <Button variant="secondary" onClick={() => setStep(at.length - 1)}>
              Skip to the result
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => {
              setStep(0)
              setRun((r) => r + 1)
            }}
          >
            <ReplayIcon /> Replay
          </Button>
          <Button variant="secondary" onClick={() => navigate('/app', { state: { prompt: rec.prompt } })}>
            <PlayIcon /> Run it live
          </Button>
        </>
      }
    />
  )
}
