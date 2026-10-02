import type { DatasetTable } from '../../api/types.ts'

/**
 * Projects made from an uploaded file. The backend can't store them (no upload endpoint, and it stays
 * unchanged), so they live in this browser's IndexedDB. Tables can be megabytes; localStorage is too small.
 */
export interface LocalProject {
  id: string
  title: string
  fileName: string
  fileSize: number
  created_at: string
  updated_at: string
  table: DatasetTable
  note?: string
}

export type LocalMeta = Omit<LocalProject, 'table'> & { rows: number; columns: number }

const DB = 'awdax'
const STORE = 'projects'
const listeners = new Set<() => void>()

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' })
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, mode)
    const req = fn(tx.objectStore(STORE))
    tx.oncomplete = () => {
      db.close()
      resolve(req.result)
    }
    tx.onerror = () => {
      db.close()
      reject(tx.error)
    }
    tx.onabort = () => {
      db.close()
      reject(tx.error ?? new Error('Storage was blocked'))
    }
  })
}

const changed = () => listeners.forEach((l) => l())

export function onLocalChange(l: () => void) {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

export async function listLocal(): Promise<LocalMeta[]> {
  const all = await run<LocalProject[]>('readonly', (s) => s.getAll())
  return all
    .map(({ table, ...meta }) => ({ ...meta, rows: table.rows.length, columns: table.columns.length }))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
}

export const getLocal = (id: string) => run<LocalProject | undefined>('readonly', (s) => s.get(id))

export async function saveLocal(p: LocalProject) {
  await run('readwrite', (s) => s.put(p))
  changed()
}

/** The record after a rename, or null when there is nothing to write. Last updated stays as it was. */
export function renamed(p: LocalProject | undefined, title: string): LocalProject | null {
  const next = title.trim()
  return p && next ? { ...p, title: next } : null
}

/** Renames an uploaded-file chat. Read and write share one transaction, so a delete in between isn't undone. */
export async function renameLocal(id: string, title: string) {
  const db = await open()
  const wrote = await new Promise<boolean>((resolve, reject) => {
    let did = false
    const tx = db.transaction(STORE, 'readwrite')
    const store = tx.objectStore(STORE)
    const get = store.get(id)
    get.onsuccess = () => {
      const next = renamed(get.result as LocalProject | undefined, title)
      if (next) {
        store.put(next)
        did = true
      }
    }
    tx.oncomplete = () => resolve(did)
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error ?? new Error('Storage was blocked'))
  }).finally(() => db.close())
  if (wrote) changed()
}

export async function deleteLocal(id: string) {
  await run('readwrite', (s) => s.delete(id))
  try {
    localStorage.removeItem(`awdax.answers.file-${id}`)
    localStorage.removeItem(`awdax.dashboard.file-${id}`)
  } catch {
    // nothing to clean
  }
  changed()
}

export const newLocalId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
