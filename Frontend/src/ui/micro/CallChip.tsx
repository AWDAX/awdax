import { useEffect, useRef, useState } from 'react'
import type { ReactNode, SVGProps } from 'react'
import { animate } from 'motion/react'
import { EditIcon, FileIcon, SearchIcon, TerminalIcon } from '../appIcons.tsx'
import { CheckIcon, ReplayIcon } from '../icons.tsx'

export type CallChipIcon = 'terminal' | 'file' | 'search' | 'edit'
export type CallChipStatus = 'idle' | 'running' | 'done' | 'error'

export type CallChipProps = {
  icon?: CallChipIcon
  name: string
  argument?: string
  status: CallChipStatus
  /** How long the step is expected to take, for the progress wash while running. */
  expectedMs?: number
  showTimer?: boolean
  onRetry?: () => void
  className?: string
}

const ICONS: Record<CallChipIcon, (p: SVGProps<SVGSVGElement>) => ReactNode> = {
  terminal: TerminalIcon,
  file: FileIcon,
  search: SearchIcon,
  edit: EditIcon,
}
const WORD: Record<CallChipStatus, string> = { idle: 'queued', running: 'running', done: 'done', error: 'failed' }

function formatMs(ms: number) {
  return ms < 10000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`
}

/** One chip per pipeline step: a tool call with a running-progress wash that settles to a check
 * (ink) or an error (blocked), with a retry affordance. */
export function CallChip({ icon = 'terminal', name, argument, status, expectedMs = 2500, showTimer = true, onRetry, className = '' }: CallChipProps) {
  const fillRef = useRef<HTMLSpanElement>(null)
  const [ms, setMs] = useState(0)
  const Glyph = ICONS[icon]

  useEffect(() => {
    const fill = fillRef.current
    if (!fill) return
    if (status === 'running') animate(fill, { scaleX: 0.85 }, { duration: expectedMs / 1000, ease: 'linear' })
    else if (status === 'done') animate(fill, { scaleX: 1 }, { duration: 0.2, ease: 'easeOut' })
    else if (status === 'idle') animate(fill, { scaleX: 0 }, { duration: 0 })
    // 'error' leaves the wash where it stopped and only recolors it (below).
  }, [status, expectedMs])

  useEffect(() => {
    if (status !== 'running') return undefined
    const startedAt = performance.now()
    const reset = window.setTimeout(() => setMs(0), 0)
    const id = window.setInterval(() => setMs(performance.now() - startedAt), 100)
    return () => {
      window.clearTimeout(reset)
      window.clearInterval(id)
    }
  }, [status])

  const tone = status === 'error' ? 'text-blocked' : status === 'done' ? 'text-ink' : 'text-ink-2'

  return (
    <span
      role="status"
      aria-busy={status === 'running' || undefined}
      className={`relative inline-flex h-8 items-center gap-1.5 overflow-hidden rounded-control border-2 border-ink bg-surface px-2.5 font-mono text-micro ${tone} ${className}`}
    >
      <span
        ref={fillRef}
        aria-hidden
        className={`absolute inset-0 origin-left scale-x-0 ${status === 'error' ? 'bg-blocked/15' : 'bg-signal-soft'}`}
      />
      <Glyph className="relative shrink-0" />
      <span className="relative font-semibold">{name}</span>
      {argument && <span className="relative truncate text-ink-3">{argument}</span>}
      {showTimer && <span className="relative shrink-0 tabular-nums text-ink-3">{status === 'idle' ? '—' : formatMs(ms)}</span>}
      {status === 'done' && <CheckIcon className="relative shrink-0" />}
      {status === 'error' && onRetry && (
        <button
          type="button"
          onClick={onRetry}
          aria-label={`Retry ${name}`}
          className="relative ml-0.5 inline-flex shrink-0 items-center rounded-control transition-colors duration-300 ease-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          <ReplayIcon />
        </button>
      )}
      <span className="sr-only">
        {name} {argument}, {WORD[status]}
      </span>
    </span>
  )
}
