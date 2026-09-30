import { useEffect, useRef } from 'react'

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Keeps keyboard focus inside an open dialog or menu: focuses its first control on open, cycles Tab and
 * Shift+Tab within it, optionally moves between items with the arrow keys (menus), and returns focus to
 * whatever opened it on close.
 */
export function useFocusTrap<T extends HTMLElement>(active: boolean, opts: { arrows?: boolean } = {}) {
  const ref = useRef<T>(null)
  const arrows = opts.arrows ?? false

  useEffect(() => {
    const box = ref.current
    if (!active || !box) return
    const opener = document.activeElement as HTMLElement | null
    const items = () => [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null)
    // A frame later: a popover is measured invisibly first, and a hidden element can't take focus.
    const first = requestAnimationFrame(() => items()[0]?.focus())

    const onKey = (e: KeyboardEvent) => {
      const list = items()
      if (list.length === 0) return
      const at = list.indexOf(document.activeElement as HTMLElement)
      if (e.key === 'Tab') {
        e.preventDefault()
        const next = e.shiftKey ? (at <= 0 ? list.length - 1 : at - 1) : at === list.length - 1 ? 0 : at + 1
        list[next].focus()
      } else if (arrows && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        e.preventDefault()
        list[(at + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length].focus()
      } else if (arrows && (e.key === 'Home' || e.key === 'End')) {
        e.preventDefault()
        list[e.key === 'Home' ? 0 : list.length - 1].focus()
      }
    }
    box.addEventListener('keydown', onKey)
    return () => {
      cancelAnimationFrame(first)
      box.removeEventListener('keydown', onKey)
      if (opener && document.contains(opener)) opener.focus()
    }
  }, [active, arrows])

  return ref
}
