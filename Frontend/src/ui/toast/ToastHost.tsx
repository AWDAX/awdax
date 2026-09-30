import { useCallback, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence } from 'motion/react'
import { ToastContext } from './toastContext.ts'
import type { ToastOptions, ToastRecord } from './toastContext.ts'
import { SwipeToast } from './SwipeToast.tsx'

let seq = 0

/** Mounts the toast stack (bottom-right on desktop, bottom on mobile) and provides `useToast()`
 * to everything under it. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastRecord[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const toast = useCallback((options: ToastOptions) => {
    seq += 1
    const id = `toast-${seq}`
    setToasts((list) => [...list, { id, duration: 5000, tone: 'default', ...options }])
    return id
  }, [])

  const value = useMemo(() => ({ toast, dismiss }), [toast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-4 sm:items-end"
      >
        <AnimatePresence>
          {toasts.map((record) => (
            <SwipeToast key={record.id} record={record} onDismiss={dismiss} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
