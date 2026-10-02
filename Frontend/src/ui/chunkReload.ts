const CHUNK_PATTERNS = [
  'failed to fetch dynamically imported module',
  'importing a module script failed',
  'error loading dynamically imported module',
  'loading chunk',
  'loading css chunk',
  'chunkloaderror',
]

export const RELOAD_KEY = 'awdax.chunk-reload-at'
const WINDOW_MS = 30_000

/**
 * A lazy chunk that no longer exists: after a deploy an open tab asks for an old hashed file and the host
 * answers with index.html, so the import fails. The wording differs per browser.
 */
export function isChunkLoadError(err: unknown): boolean {
  if (err === null || err === undefined) return false
  const name = typeof err === 'object' && 'name' in err ? String((err as { name: unknown }).name) : ''
  const message = err instanceof Error ? err.message : typeof err === 'string' ? err : ''
  const text = `${name} ${message}`.toLowerCase()
  return CHUNK_PATTERNS.some((p) => text.includes(p))
}

/** True when this tab never auto-reloaded, or did so longer ago than the window (stops reload loops). */
export function shouldAutoReload(now: number, lastReloadAt: number | null, windowMs = WINDOW_MS): boolean {
  return lastReloadAt === null || now - lastReloadAt > windowMs
}

type ReloadStorage = Pick<Storage, 'getItem' | 'setItem'>

/**
 * Reloads at most once per window, remembered in sessionStorage. Blocked storage means no reload at all:
 * without a memory of the last reload a broken chunk would loop forever.
 */
export function reloadOnce(storage: ReloadStorage, now: number, reload: () => void): boolean {
  try {
    const raw = storage.getItem(RELOAD_KEY)
    const last = raw === null ? null : Number(raw)
    if (!shouldAutoReload(now, last === null || Number.isNaN(last) ? null : last)) return false
    storage.setItem(RELOAD_KEY, String(now))
  } catch {
    return false
  }
  reload()
  return true
}

/** Vite fires `vite:preloadError` when a dynamic import's preload fails; take it over and reload once. */
export function installChunkReload(
  target: Pick<Window, 'addEventListener'>,
  getStorage: () => ReloadStorage,
  now: () => number,
  reload: () => void,
): void {
  target.addEventListener('vite:preloadError', (event) => {
    event.preventDefault()
    try {
      reloadOnce(getStorage(), now(), reload)
    } catch {
      // sessionStorage itself can throw on access: stay put
    }
  })
}
