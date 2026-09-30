import { useSyncExternalStore } from 'react'

/**
 * Row alerts (the BellToggle): which chats this browser watches, and how many rows each had when last seen.
 * Kept in localStorage; a personal preference, not shared data.
 */
type Store = Record<string, { watched: boolean; seen: number }>
const KEY = 'awdax.alerts'
const listeners = new Set<() => void>()

let cache: Store | null = null
function read(): Store {
  if (cache) return cache
  try {
    cache = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Store
  } catch {
    cache = {}
  }
  return cache
}
function write(next: Store) {
  cache = next
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // blocked storage: alerts last for this tab only
  }
  listeners.forEach((l) => l())
}

function subscribe(l: () => void) {
  listeners.add(l)
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
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
