const OPEN = 1
const CLOSED = 2
// Spread simultaneous reconnects from many tabs after a backend restart.
const JITTER_MS = 250

export type SseLike = {
  readyState: number
  close: () => void
  addEventListener: (type: 'open' | 'error', listener: () => void) => void
}

type Options = {
  open: () => SseLike
  schedule: (fn: () => void, ms: number) => number
  cancel: (handle: number) => void
  baseMs?: number
  maxMs?: number
  random?: () => number
  onError?: () => void
}

export type SseSupervisor = {
  start: () => void
  stop: () => void
  isOpen: () => boolean
}

/**
 * Keeps one EventSource alive. A browser reconnects by itself only while the stream was open; when the
 * response is not a 200 event stream (503 during a restart, 401 on an expired cookie) it closes the source for
 * good, so the supervisor reopens it with exponential backoff.
 */
export function createSseSupervisor(options: Options): SseSupervisor {
  const { open, schedule, cancel, baseMs = 1000, maxMs = 30_000, random = Math.random, onError } = options
  let source: SseLike | null = null
  let timer: number | undefined
  let attempt = 0

  const connect = () => {
    timer = undefined
    const next = open()
    source = next
    next.addEventListener('open', () => {
      if (source === next) attempt = 0
    })
    next.addEventListener('error', () => {
      if (source !== next) return
      onError?.()
      // Still CONNECTING: the browser is already retrying a stream that had been open.
      if (next.readyState !== CLOSED) return
      next.close()
      source = null
      const delay = Math.min(maxMs, baseMs * 2 ** attempt + random() * JITTER_MS)
      attempt += 1
      timer = schedule(connect, delay)
    })
  }

  return {
    start: () => {
      if (source || timer !== undefined) return
      connect()
    },
    stop: () => {
      if (timer !== undefined) cancel(timer)
      timer = undefined
      source?.close()
      source = null
      attempt = 0
    },
    isOpen: () => source?.readyState === OPEN,
  }
}
