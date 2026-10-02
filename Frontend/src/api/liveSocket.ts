// A proxy can hold a handshake open without ever firing open or close; stop waiting after this long.
const CONNECT_TIMEOUT_MS = 10_000

/**
 * Live updates over a WebSocket. Repeated failed or short-lived connections
 * hand off to the server-sent event stream instead of flooding the dev proxy.
 */
export function openLiveSocket(
  url: string,
  handlers: {
    onMessage: (message: unknown) => void
    onConnection: (state: 'open' | 'reconnecting') => void
    onFallback: () => void
  },
): () => void {
  let socket: WebSocket | null = null
  let closed = false
  let gaveUp = false
  let attempts = 0
  let failures = 0
  let timer = 0
  let watchdog = 0

  const connect = () => {
    if (closed || gaveUp) return
    let openedAt = 0
    try {
      socket = new WebSocket(url)
    } catch {
      gaveUp = true
      handlers.onFallback()
      return
    }
    // Hold this attempt's socket: `socket` changes with every reconnect.
    const current = socket
    watchdog = window.setTimeout(() => {
      if (current.readyState === WebSocket.CONNECTING) current.close()
    }, CONNECT_TIMEOUT_MS)
    socket.addEventListener('open', () => {
      window.clearTimeout(watchdog)
      openedAt = Date.now()
      attempts = 0
      handlers.onConnection('open')
    })
    socket.addEventListener('message', (event) => {
      try {
        handlers.onMessage(JSON.parse(String(event.data)))
      } catch {
        // A malformed frame is skipped; the next one still applies.
      }
    })
    socket.addEventListener('close', () => {
      window.clearTimeout(watchdog)
      socket = null
      if (closed || gaveUp) return
      // Dev proxies can accept the handshake, then abort the stream 10-20 seconds later.
      // Only a connection that stayed up for a full minute clears the failure streak.
      failures = openedAt && Date.now() - openedAt >= 60_000 ? 0 : failures + 1
      if (failures >= 2) {
        gaveUp = true
        handlers.onFallback()
        return
      }
      attempts += 1
      handlers.onConnection('reconnecting')
      const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempts, 5))
      timer = window.setTimeout(connect, delay)
    })
  }

  const onVisibility = () => {
    if (document.visibilityState === 'visible' && !socket && !closed && !gaveUp) {
      window.clearTimeout(timer)
      attempts = 0
      connect()
    }
  }

  document.addEventListener('visibilitychange', onVisibility)
  connect()
  return () => {
    closed = true
    window.clearTimeout(timer)
    window.clearTimeout(watchdog)
    socket?.close()
    document.removeEventListener('visibilitychange', onVisibility)
  }
}
