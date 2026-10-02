import { createContext, useContext } from 'react'
import type { InstanceSummary } from './types.ts'

export type Instances = {
  /** Every chat, most recently updated first (the backend's order). */
  list: InstanceSummary[]
  /** True until the first list arrives. */
  loading: boolean
  /** The last load error, e.g. the backend is down. Cleared by the next good load. */
  error: string | null
  /** True after the latest accepted list read succeeded; false after a failed read and before the first. */
  listOk: boolean
  refresh: () => Promise<void>
  /** Adds or updates one chat in the list without waiting for a refresh. */
  upsert: (item: InstanceSummary) => void
  /** Deletes on the backend, then removes the chat from the list. */
  remove: (id: string) => Promise<void>
  /** Persists a new title on the backend and updates the list. */
  rename: (id: string, title: string) => Promise<void>
}

export const InstancesContext = createContext<Instances | null>(null)

export function useInstances(): Instances {
  const value = useContext(InstancesContext)
  if (!value) throw new Error('useInstances must be used inside <InstancesProvider>')
  return value
}
