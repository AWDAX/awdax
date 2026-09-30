import { useEffect, useRef, useState } from 'react'
import { animate, useReducedMotion } from 'motion/react'
import { BellIcon, BellOffIcon } from '../appIcons.tsx'

export type BellToggleSize = 'sm' | 'md'

export type BellToggleProps = {
  pressed?: boolean
  defaultPressed?: boolean
  onChange?: (pressed: boolean) => void
  count?: number
  size?: BellToggleSize
  offLabel?: string
  onLabel?: string
  /** Hide the label text, keep it in the aria-label. */
  iconOnly?: boolean
  disabled?: boolean
  className?: string
}

// md matches buttonClass md (h-10, px-4, text-small), so it lines up with the buttons beside it.
const SIZE: Record<BellToggleSize, string> = { sm: 'h-8 px-2 text-micro', md: 'h-10 px-4 text-small' }

/** Per-project "alert me about new rows" toggle, with a small ring wobble on the bell when it
 * turns on and a count badge while armed. */
export function BellToggle({
  pressed,
  defaultPressed = false,
  onChange,
  count = 0,
  size = 'md',
  offLabel = 'Notify me',
  onLabel = "You'll be notified",
  iconOnly = false,
  disabled = false,
  className = '',
}: BellToggleProps) {
  const [inner, setInner] = useState(defaultPressed)
  const on = pressed ?? inner
  const reduceMotion = useReducedMotion()
  const bellRef = useRef<HTMLSpanElement>(null)
  const prevOn = useRef(on)

  useEffect(() => {
    if (on && !prevOn.current && !reduceMotion && bellRef.current) {
      animate(
        bellRef.current,
        { rotate: [0, -14, 10, -6, 3, 0] },
        { duration: 0.6, ease: [0.65, 0, 0.35, 1] },
      )
    }
    prevOn.current = on
  }, [on, reduceMotion])

  const toggle = () => {
    if (pressed === undefined) setInner(!on)
    onChange?.(!on)
  }

  const label = on ? onLabel : offLabel
  const showBadge = on && count > 0

  return (
    <button
      type="button"
      disabled={disabled}
      aria-pressed={on}
      aria-label={iconOnly ? label : undefined}
      onClick={toggle}
      className={
        `relative inline-flex items-center gap-2 rounded-control border-2 border-ink font-semibold transition-[background-color,color,scale] duration-300 ease-soft active:scale-97 ` +
        `disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink ` +
        `${on ? 'bg-ink text-signal' : 'bg-surface text-ink hover:bg-sunken'} ${SIZE[size]} ${className}`
      }
    >
      <span ref={bellRef} className="relative inline-flex shrink-0" style={{ transformOrigin: '50% 20%' }}>
        {on ? <BellIcon /> : <BellOffIcon />}
        {showBadge && (
          <span
            aria-hidden
            className="absolute -top-1.5 -right-1.5 inline-flex h-3.5 min-w-3.5 items-center justify-center rounded-control bg-signal px-0.5 text-[9px] font-bold text-on-signal"
          >
            {count > 9 ? '9+' : count}
          </span>
        )}
      </span>
      {!iconOnly && <span>{label}</span>}
    </button>
  )
}
