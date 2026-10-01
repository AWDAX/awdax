import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { TrashIcon } from '../appIcons.tsx'
import { CheckIcon, ReplayIcon } from '../icons.tsx'

export type FuseButtonSize = 'sm' | 'md'
export type FuseCommitOn = 'press' | 'fuseEnd'
type Phase = 'idle' | 'armed' | 'settled'

export type FuseButtonProps = {
  label?: string
  undoLabel?: string
  doneLabel?: string
  icon?: ReactNode
  /** Where the fuse bar draws: bottom edge or top edge of the pressed state. */
  fusePosition?: 'bottom' | 'top'
  undoWindow?: number
  commitOn?: FuseCommitOn
  onCommit?: () => void
  onUndo?: () => void
  size?: FuseButtonSize
  disabled?: boolean
  tone?: 'danger' | 'default'
  /** Compact icon-only variant for a 24-28px row action (e.g. the trash button in chat history). */
  iconOnly?: boolean
  className?: string
}

// md matches buttonClass md (h-10, px-4, text-small), so it lines up with the buttons beside it.
const SIZE: Record<FuseButtonSize, string> = { sm: 'h-8 px-2.5 text-micro', md: 'h-10 px-4 text-small' }

/** A destructive action with an undo window: press arms a fuse, the fuse burns down and commits
 * unless undone. `tone="danger"` (delete, reset) burns in blocked red; default burns in signal. */
export function FuseButton({
  label = 'Delete',
  undoLabel = 'Undo',
  doneLabel = 'Deleted',
  icon,
  fusePosition = 'bottom',
  undoWindow = 5000,
  commitOn = 'fuseEnd',
  onCommit,
  onUndo,
  size = 'md',
  disabled = false,
  tone = 'default',
  iconOnly = false,
  className = '',
}: FuseButtonProps) {
  const [phase, setPhase] = useState<Phase>('idle')
  const fuseRef = useRef<HTMLSpanElement>(null)
  const animRef = useRef<Animation | null>(null)

  const arm = () => {
    if (disabled || phase !== 'idle') return
    setPhase('armed')
    if (commitOn === 'press') onCommit?.()
  }
  const undo = () => {
    if (phase !== 'armed') return
    animRef.current?.cancel()
    onUndo?.()
    setPhase('idle')
  }

  useEffect(() => {
    if (phase !== 'armed' || !fuseRef.current) return undefined
    const anim = fuseRef.current.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], {
      duration: undoWindow,
      easing: 'linear',
      fill: 'forwards',
    })
    anim.onfinish = () => {
      if (commitOn === 'fuseEnd') onCommit?.()
      setPhase('settled')
    }
    animRef.current = anim
    return () => anim.cancel()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, undoWindow, commitOn])

  // The "done" tick shows briefly, then the button is ready again (a Reset can be used more than once).
  useEffect(() => {
    if (phase !== 'settled') return undefined
    const t = window.setTimeout(() => setPhase('idle'), 1600)
    return () => window.clearTimeout(t)
  }, [phase])

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Escape' && phase === 'armed') undo()
  }

  const fuseColor = tone === 'danger' ? 'bg-blocked' : 'bg-signal'

  const isIdle = phase === 'idle'
  const isArmed = phase === 'armed'
  const isSettled = phase === 'settled'

  const baseClass = isSettled
    ? `inline-flex text-left items-center justify-center overflow-hidden rounded-control border-2 border-line font-semibold text-ink-3 ${SIZE[size]} ${className}`
    : isArmed
    ? `relative inline-flex text-left items-center justify-center overflow-hidden rounded-control border-2 border-ink bg-surface font-semibold text-ink transition-colors duration-300 ease-soft hover:bg-sunken focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink ${SIZE[size]} ${className}`
    : `inline-flex text-left items-center justify-center overflow-hidden rounded-control border-2 font-semibold transition-[background-color,border-color,color,scale] duration-300 ease-soft active:scale-97 disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink ${tone === 'danger' ? 'border-blocked text-blocked hover:bg-blocked/10' : 'border-ink text-ink hover:bg-sunken'} ${SIZE[size]} ${className}`


  return (
    <button
      type="button"
      disabled={disabled || isSettled}
      onClick={isArmed ? undo : arm}
      onKeyDown={isArmed ? onKeyDown : undefined}
      aria-label={iconOnly ? (isArmed ? `${undoLabel}: ${label}` : label) : undefined}
      title={isArmed ? `${undoLabel} (Esc)` : (iconOnly ? label : undefined)}
      className={baseClass}
    >
      <span className="grid text-left">
        <span className={`col-start-1 row-start-1 inline-flex items-center gap-2 transition-opacity duration-300 ${isIdle ? 'opacity-100' : 'opacity-0 invisible'}`} aria-hidden={!isIdle}>
          {icon ?? <TrashIcon />}
          {!iconOnly && label}
        </span>
        <span className={`col-start-1 row-start-1 inline-flex items-center gap-2 transition-opacity duration-300 ${isArmed ? 'opacity-100' : 'opacity-0 invisible'}`} aria-hidden={!isArmed}>
          <ReplayIcon />
          {!iconOnly && undoLabel}
        </span>
        <span className={`col-start-1 row-start-1 inline-flex items-center gap-2 transition-opacity duration-300 ${isSettled ? 'opacity-100' : 'opacity-0 invisible'}`} aria-hidden={!isSettled}>
          <CheckIcon />
          {!iconOnly && doneLabel}
        </span>
      </span>
      {isArmed && (
        <span
          ref={fuseRef}
          aria-hidden
          className={`absolute inset-x-0 h-0.5 origin-right ${fusePosition === 'top' ? 'top-0' : 'bottom-0'} ${fuseColor}`}
        />
      )}
    </button>
  )
}
