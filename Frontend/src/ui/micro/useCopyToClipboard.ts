import { useCallback, useEffect, useRef, useState } from 'react'

export type CopyState = 'idle' | 'done' | 'error'

type Options = {
  onCopySuccess?: (text: string) => void
  onCopyError?: (error: Error) => void
  resetDelay?: number
}

// Adapted from ncdai/chanhdai.com's use-copy-to-clipboard (MIT), with the haptics/analytics deps
// dropped (no new packages).
export function useCopyToClipboard({ onCopySuccess, onCopyError, resetDelay = 1500 }: Options = {}) {
  const [state, setState] = useState<CopyState>('idle')
  const resetTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(
    () => () => {
      if (resetTimeout.current) clearTimeout(resetTimeout.current)
    },
    [],
  )

  const copy = useCallback(
    async (text: string | (() => string)) => {
      if (resetTimeout.current) clearTimeout(resetTimeout.current)
      try {
        const finalText = typeof text === 'function' ? text() : text
        await navigator.clipboard.writeText(finalText)
        setState('done')
        onCopySuccess?.(finalText)
      } catch (error) {
        setState('error')
        onCopyError?.(error instanceof Error ? error : new Error('Copy failed'))
      } finally {
        if (resetTimeout.current) clearTimeout(resetTimeout.current)
        resetTimeout.current = setTimeout(() => setState('idle'), resetDelay)
      }
    },
    [onCopySuccess, onCopyError, resetDelay],
  )

  return { state, copy } as const
}
