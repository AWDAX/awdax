import { useCallback, useState } from 'react'
import { scopedKey } from '../auth/userScope.ts'
import type { Visit } from './buildSources.ts'

const key = (id: string) => scopedKey(`awdax.visits.${id}`)
const MAX = 60

function load(id: string): Visit[] {
  try {
    const v = JSON.parse(localStorage.getItem(key(id)) ?? '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
}

/**
 * The pages the backend has been reading for one chat, in order, from the live stream's `current_source`.
 * Kept in this browser (the backend only reports the current page), newest last, at most 60.
 */
export function useVisits(instanceId: string) {
  const [visits, setVisits] = useState<Visit[]>(() => load(instanceId))

  const record = useCallback(
    (source: string | undefined, phase?: string) => {
      if (!source) return
      setVisits((prev) => {
        if (prev[prev.length - 1]?.source === source) return prev
        const next = [...prev, { source, phase, at: new Date().toISOString() }].slice(-MAX)
        try {
          localStorage.setItem(key(instanceId), JSON.stringify(next))
        } catch {
          // storage full or blocked: the history lasts for this visit only
        }
        return next
      })
    },
    [instanceId],
  )

  return { visits, record }
}
