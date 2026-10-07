import { useSyncExternalStore } from 'react'
import { onScopeChange, scopedKey } from '../auth/userScope.ts'

/**
 * Row alerts (the BellToggle): which chats this browser watches, and how many rows each had when last seen.
 * Kept in localStorage; a personal preference, not shared data.
 */
type Store = Record<string, { watched: boolean; seen: number }>
const BASE_KEY = 'awdax.alerts'
// Named for the signed-in account, so another account on this browser never sees these flags.
const key = () => scopedKey(BASE_KEY)
const listeners = new Set<() => void>()

let cache: Store | null = null
// A different account is showing: what was cached belongs to the previous one.
onScopeChange(() => {
  cache = null
  listeners.forEach((l) => l())
})
function read(): Store {
  if (cache) return cache
  try {
    cache = JSON.parse(localStorage.getItem(key()) ?? '{}') as Store
  } catch {
    cache = {}
  }
  return cache
}
function write(next: Store) {
  cache = next
  try {
    localStorage.setItem(key(), JSON.stringify(next))
  } catch {
    // blocked storage: alerts last for this tab only
  }
  listeners.forEach((l) => l())
}

function subscribe(l: () => void) {
  listeners.add(l)
  const onStorage = (e: StorageEvent) => {
    if (e.key === key()) {
      cache = null
      l()
    }
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(l)
    window.removeEventListener('storage', onStorage)
  }
}

export function useAlerts(): Store {
  return useSyncExternalStore(subscribe, read, () => ({}))
}

export function setWatched(id: string, watched: boolean, rows: number) {
  const s = read()
  write({ ...s, [id]: { watched, seen: s[id]?.seen ?? rows } })
  if (watched && 'Notification' in window && Notification.permission === 'default') void Notification.requestPermission()
}

export function markSeen(id: string, rows: number) {
  const s = read()
  if (s[id] && s[id].seen === rows) return
  write({ ...s, [id]: { watched: s[id]?.watched ?? false, seen: rows } })
}

/** A system notification when the tab is in the background and permission was given; the toast covers the rest. */
export function notify(title: string, body: string) {
  if (!('Notification' in window) || Notification.permission !== 'granted' || !document.hidden) return
  try {
    new Notification(title, { body, tag: 'awdax-rows' })
  } catch {
    // some browsers only allow notifications from a service worker
  }
}

/** Flags saved before alerts were per account sit under one shared key. Move those for chats this account owns. */
export function adoptLegacyAlerts(ownedIds: Iterable<string>) {
  try {
    const raw = localStorage.getItem(BASE_KEY)
    if (raw === null) return
    const legacy = JSON.parse(raw) as Store
    const mine: Store = {}
    const rest: Store = { ...legacy }
    for (const id of ownedIds) {
      if (id in legacy) {
        mine[id] = legacy[id]
        delete rest[id]
      }
    }
    if (!Object.keys(mine).length) return
    write({ ...mine, ...read() })
    if (Object.keys(rest).length) localStorage.setItem(BASE_KEY, JSON.stringify(rest))
    else localStorage.removeItem(BASE_KEY)
  } catch {
    // unreadable or blocked storage: nothing to move
  }
}
