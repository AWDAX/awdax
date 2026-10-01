import { useId, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { m } from 'motion/react'
import { ChevronIcon } from './appIcons.tsx'
import { CheckIcon } from './icons.tsx'
import { EASE_SOFT } from './motion.ts'
import { Popover } from './Popover.tsx'

export type SelectOption<T> = { value: T; label: string; disabled?: boolean }

type Props<T> = {
  value: T
  options: readonly SelectOption<T>[]
  onChange: (value: T) => void
  /** Accessible name, e.g. "Sort projects". */
  label: string
  className?: string
}

/**
 * A single-choice dropdown in the design system (the native <select> list can't be styled). It opens in a
 * Popover, marks the current choice with a tick, and works like a native one from the keyboard: arrows, Home,
 * End, Enter or Space to pick, Escape or Tab to close. Pattern copied from TileMenu (Popover + focus on open).
 */
export function Select<T>({ value, options, onChange, label, className = '' }: Props<T>) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [width, setWidth] = useState(0)
  const button = useRef<HTMLButtonElement>(null)
  const list = useRef<HTMLDivElement>(null)
  const id = useId()
  const at = Math.max(0, options.findIndex((o) => o.value === value))

  const show = () => {
    let focusIndex = at
    if (options[focusIndex]?.disabled) {
      focusIndex = Math.max(0, options.findIndex(o => !o.disabled))
    }
    setActive(focusIndex)
    setWidth(button.current?.offsetWidth ?? 0)
    setOpen(true)
    // A frame later: the popover is measured invisibly first, and a hidden element can't take focus.
    requestAnimationFrame(() => list.current?.focus())
  }
  const hide = (refocus: boolean) => {
    setOpen(false)
    if (refocus) button.current?.focus()
  }
  const pick = (i: number) => {
    if (options[i].disabled) return
    if (options[i].value !== value) onChange(options[i].value)
    hide(true)
  }

  const findNext = (start: number, step: 1 | -1) => {
    for (let i = start + step; i >= 0 && i < options.length; i += step) {
      if (!options[i].disabled) return i
    }
    return start
  }

  const onButtonKey = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
      e.preventDefault()
      show()
    }
  }
  const onListKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive(findNext(active, 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive(findNext(active, -1))
    } else if (e.key === 'Home') {
      e.preventDefault()
      setActive(findNext(-1, 1))
    } else if (e.key === 'End') {
      e.preventDefault()
      setActive(findNext(options.length, -1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      pick(active)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      hide(true)
    } else if (e.key === 'Tab') {
      hide(false)
    }
  }

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`${label}: ${options[at]?.label ?? ''}`}
        onClick={() => (open ? hide(false) : show())}
        onKeyDown={onButtonKey}
        className={
          'group inline-flex h-9 items-center justify-between gap-3 rounded-control border-2 bg-surface pr-2 pl-2.5 text-small font-medium ' +
          'transition-[border-color,background-color] duration-300 ease-soft hover:border-ink focus-visible:border-ink focus-visible:outline-none ' +
          `${open ? 'border-ink bg-sunken' : 'border-line'} ${className}`
        }
      >
        <span className="truncate">{options[at]?.label}</span>
        <ChevronIcon className={`shrink-0 text-ink-2 transition-transform duration-300 ease-soft ${open ? '-rotate-90' : 'rotate-90'}`} />
      </button>
      <Popover anchor={button} open={open} onClose={() => hide(false)} align="end" className="overflow-hidden">
        <m.div
          ref={list}
          role="listbox"
          tabIndex={-1}
          aria-label={label}
          aria-activedescendant={`${id}-${active}`}
          onKeyDown={onListKey}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: EASE_SOFT }}
          style={{ minWidth: Math.max(176, width) }}
          className="flex flex-col p-1 outline-none"
        >
          {options.map((o, i) => {
            const selected = o.value === value
            return (
              <div
                key={String(o.value)}
                id={`${id}-${i}`}
                role="option"
                aria-selected={selected}
                aria-disabled={o.disabled}
                onPointerEnter={() => !o.disabled && setActive(i)}
                onClick={() => !o.disabled && pick(i)}
                className={`flex ${o.disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} items-center justify-between gap-4 rounded-control px-2.5 py-2 text-small transition-colors duration-200 ease-soft ${
                  i === active && !o.disabled ? 'bg-sunken text-ink' : 'text-ink-2'
                } ${selected ? 'font-semibold text-ink' : ''}`}
              >
                <span className="flex items-center gap-2.5">
                  <span aria-hidden className={`h-4 w-1 rounded-full transition-colors duration-200 ease-soft ${selected ? 'bg-signal' : 'bg-transparent'}`} />
                  {o.label}
                </span>
                {selected && <CheckIcon className="shrink-0" />}
              </div>
            )
          })}
        </m.div>
      </Popover>
    </>
  )
}
