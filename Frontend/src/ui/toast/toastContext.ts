import { createContext, useContext } from 'react'

export type ToastTone = 'default' | 'success' | 'error'

export type ToastOptions = {
  title: string
  description?: string
  tone?: ToastTone
  actionLabel?: string
  onAction?: () => void
  /** Milliseconds before it auto-dismisses. 0 disables the fuse. */
  duration?: number
}

export type ToastRecord = ToastOptions & { id: string }

export type ToastContextValue = {
  toast: (options: ToastOptions) => string
  dismiss: (id: string) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

/** `toast({ title, ... })` / `dismiss(id)`. Must be used under `<ToastProvider>`. */
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
