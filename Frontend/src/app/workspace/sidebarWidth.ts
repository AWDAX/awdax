type Reader = Pick<Storage, 'getItem'> | null
type Writer = Pick<Storage, 'setItem'> | null

export const SIDEBAR_MIN = 220
export const SIDEBAR_MAX = 420
export const SIDEBAR_DEFAULT = 264
export const WIDTH_KEY = 'awdax.sidebar.width'

/** Reading `localStorage` itself can throw when site data is blocked. */
export function browserStorage(): Storage | null {
  try {
    return localStorage
  } catch {
    return null
  }
}

export function clampWidth(px: number): number {
  if (!Number.isFinite(px)) return SIDEBAR_DEFAULT
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, Math.round(px)))
}

/** The width the user dragged the sidebar to. Blocked storage or a garbage value gives the default. */
export function readWidth(storage: Reader): number {
  if (!storage) return SIDEBAR_DEFAULT
  try {
    const saved = storage.getItem(WIDTH_KEY)
    return saved === null ? SIDEBAR_DEFAULT : clampWidth(Number.parseFloat(saved))
  } catch {
    return SIDEBAR_DEFAULT
  }
}

export function writeWidth(storage: Writer, px: number): void {
  if (!storage) return
  try {
    storage.setItem(WIDTH_KEY, String(clampWidth(px)))
  } catch {
    // storage blocked: the sidebar just forgets its width
  }
}
