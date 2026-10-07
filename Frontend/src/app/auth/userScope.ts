/**
 * Which account this tab is showing. Everything the app keeps in localStorage for a chat (saved answers,
 * dashboards, graph layouts, visited pages, alerts) is named with it, so two accounts that share a browser never
 * read each other's saved data. Pure apart from the optional storage argument, so Node tests can run it.
 */
let current: string | null = null
const listeners = new Set<() => void>()

/** Called by the auth layer when an account is confirmed (or on sign-out, with null). */
export function setScopeUser(id: string | null) {
  if (id === current) return
  current = id
  listeners.forEach((l) => l())
}

/** `base` named for the signed-in account. With nobody signed in it names a key nothing else uses. */
export function scopedKey(base: string): string {
  return `${base}:${current ?? 'signed-out'}`
}

/** Runs when the account changes, so a module can drop what it cached for the previous one. */
export function onScopeChange(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

type KeyStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/**
 * Entries saved before keys were per account sit under `<prefix><chat id>`. Move those that belong to chats this
 * account owns to their scoped key. Entries for chats it does not own are left alone: nothing reads them any more.
 */
export function adoptUnscopedKeys(prefixes: string[], ownedIds: Iterable<string>, store: KeyStore = localStorage): void {
  try {
    for (const id of ownedIds) {
      for (const prefix of prefixes) {
        const old = `${prefix}${id}`
        const value = store.getItem(old)
        if (value === null) continue
        const next = scopedKey(old)
        if (store.getItem(next) === null) store.setItem(next, value)
        store.removeItem(old)
      }
    }
  } catch {
    // blocked storage: nothing to move
  }
}

/** The per-chat prefixes `adoptUnscopedKeys` moves. */
export const CHAT_KEY_PREFIXES = ['awdax.answers.', 'awdax.dashboard.v2.', 'awdax.graphs.v2.', 'awdax.visits.']
