import { useEffect, useRef } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { animate, m, useMotionValue, useReducedMotion } from 'motion/react'
import { CloseIcon } from '../appIcons.tsx'
import type { ToastRecord } from './toastContext.ts'

type Props = {
  record: ToastRecord
  onDismiss: (id: string) => void
}

const SWIPE_DISTANCE = 40
const EASE_SOFT = [0.33, 1, 0.68, 1] as const

/** One toast: swipe down (or right on desktop) to dismiss, Escape to close, a fuse bar burns down
 * to the auto-dismiss, paused on hover or focus. */
export function SwipeToast({ record, onDismiss }: Props) {
  const reduceMotion = useReducedMotion()
  const { id, title, description, tone = 'default', actionLabel, onAction, duration = 5000 } = record
  const cardRef = useRef<HTMLDivElement>(null)
  const fuseRef = useRef<HTMLSpanElement>(null)
  const fuseAnim = useRef<Animation | null>(null)
  const dragStartY = useRef<number | null>(null)
  const y = useMotionValue(0)

  const fuseColor = tone === 'error' ? 'var(--color-blocked)' : 'var(--color-signal)'

  useEffect(() => {
    if (duration <= 0 || !fuseRef.current) return undefined
    const anim = fuseRef.current.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], {
      duration,
      easing: 'linear',
      fill: 'forwards',
    })
    anim.onfinish = () => onDismiss(id)
    fuseAnim.current = anim
    return () => anim.cancel()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [duration, id])

  const pause = () => fuseAnim.current?.pause()
  const resume = () => {
    if (fuseAnim.current?.playState === 'paused') fuseAnim.current.play()
  }

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).closest('button')) return
    dragStartY.current = e.clientY - y.get()
    cardRef.current?.setPointerCapture(e.pointerId)
    pause()
  }
  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (dragStartY.current === null) return
    y.set(Math.max(0, e.clientY - dragStartY.current))
  }
  const onPointerUp = () => {
    if (dragStartY.current === null) return
    dragStartY.current = null
    const dy = y.get()
    if (dy > SWIPE_DISTANCE) {
      if (!reduceMotion) animate(y, dy + 80, { duration: 0.2, ease: EASE_SOFT })
      onDismiss(id)
      return
    }
    animate(y, 0, { duration: 0.3, ease: EASE_SOFT })
    resume()
  }

  return (
    <m.div
      ref={cardRef}
      role="status"
      aria-live="polite"
      aria-atomic="true"
      tabIndex={0}
      layout={!reduceMotion}
      initial={reduceMotion ? undefined : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16, transition: { duration: 0.2 } }}
      transition={{ duration: 0.45, ease: EASE_SOFT }}
      style={{ touchAction: 'none', y }}
      className="relative flex w-[min(360px,calc(100vw-2rem))] cursor-grab items-start gap-3 overflow-hidden rounded-panel border-2 border-ink bg-surface p-3 active:cursor-grabbing"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onPointerEnter={pause}
      onPointerLeave={resume}
      onFocus={pause}
      onBlur={resume}
      onKeyDown={(e) => e.key === 'Escape' && onDismiss(id)}
    >
      <span className="relative flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-small font-semibold text-ink">{title}</span>
        {description && <span className="text-micro text-ink-2">{description}</span>}
      </span>
      {actionLabel && (
        <button
          type="button"
          onClick={() => {
            onAction?.()
            onDismiss(id)
          }}
          className="relative shrink-0 rounded-control border-2 border-ink bg-surface px-2 py-1 text-micro font-semibold text-ink transition-colors duration-300 ease-soft hover:bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          {actionLabel}
        </button>
      )}
      <button
        type="button"
        aria-label="Close"
        onClick={() => onDismiss(id)}
        className="relative shrink-0 rounded-control p-0.5 text-ink-3 transition-colors duration-300 ease-soft hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <CloseIcon />
      </button>
      {duration > 0 && (
        <span
          ref={fuseRef}
          aria-hidden
          style={{ backgroundColor: fuseColor }}
          className="absolute inset-x-0 bottom-0 h-0.5 origin-left"
        />
      )}
    </m.div>
  )
}
