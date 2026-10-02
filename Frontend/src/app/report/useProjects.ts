import { useEffect, useMemo, useRef, useState } from 'react'
import { isFresh, runPool } from './pollPool.ts'
import { awdax } from '../../api/awdax.ts'
import { sortedIdKey } from '../../api/singleFlight.ts'
import { useInstances } from '../../api/instancesContext.ts'
import type { LiveSnapshot, LivePhase } from '../../api/types.ts'
import { WORKING } from '../chat/phases.ts'
import { useLocalProjects } from '../files/useLocalProjects.ts'

export type ProjectStatus = 'running' | 'live' | 'paused' | 'error' | 'idle' | 'uploaded' | 'loading'

/** One row of the projects report: a web request (backend instance) or an uploaded file. */
export interface Project {
  id: string
  kind: 'web' | 'file'
  title: string
  status: ProjectStatus
  phase?: LivePhase
  rows: number
  /** The page being read now (web) or the file name. */
  source: string
  detail: string
  cycle: number
  rowsAddedLastCycle: number
  created_at: string
  updated_at: string
  liveEnabled: boolean
  path: string
}

const REFRESH_MS = 15_000
const CONCURRENCY = 6

function statusOf(s: LiveSnapshot | undefined): ProjectStatus {
  if (!s) return 'loading'
  const phase = s.status.phase
  if (!s.live_enabled || phase === 'stopped') return 'paused'
  if (phase === 'error') return 'error'
  if (phase && WORKING.includes(phase)) return 'running'
  if (phase === 'sleep') return 'live'
  return 'idle'
}

/**
 * Every project with its live status. The backend's list has no status or row count, so this asks
 * GET /api/instances/{id}/live for each one, six at a time, every 15 seconds.
 */
export function useProjects() {
  const { list, loading } = useInstances()
  const local = useLocalProjects()
  const [snaps, setSnaps] = useState<Record<string, LiveSnapshot>>({})
  const ids = sortedIdKey(list)
  // When each project was last changed by hand (pause/resume); older in-flight polls must not undo it.
  const changedAt = useRef<Record<string, number>>({})

  useEffect(() => {
    if (!ids) return
    let alive = true
    let running = false
    const load = async () => {
      if (document.visibilityState === 'hidden') return
      if (running) return // the last cycle is still in flight
      running = true
      try {
        await runPool(ids.split(','), CONCURRENCY, async (id) => {
          const startedAt = Date.now()
          try {
            const snap = await awdax.getLive(id)
            if (alive && isFresh(startedAt, changedAt.current[id])) setSnaps((prev) => ({ ...prev, [id]: snap }))
          } catch {
            // a deleted or unreachable project keeps its last known status
          }
        }, () => alive)
      } finally {
        running = false
      }
    }
    const first = window.setTimeout(load, 0)
    const timer = window.setInterval(load, REFRESH_MS)
    return () => {
      alive = false
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [ids])

  const projects = useMemo<Project[]>(() => {
    const web: Project[] = list.map((i) => {
      const s = snaps[i.id]
      return {
        id: i.id,
        kind: 'web',
        title: i.title,
        status: statusOf(s),
        phase: s?.status.phase,
        rows: s?.rows_total ?? 0,
        source: s?.status.current_source ?? '',
        detail: s?.status.detail ?? '',
        cycle: s?.status.cycle ?? 0,
        rowsAddedLastCycle: s?.status.rows_added_last_cycle ?? 0,
        created_at: i.created_at,
        updated_at: i.updated_at,
        liveEnabled: s?.live_enabled ?? true,
        path: `/app/c/${i.id}`,
      }
    })
    const files: Project[] = local.map((p) => ({
      id: p.id,
      kind: 'file',
      title: p.title,
      status: 'uploaded',
      rows: p.rows,
      source: p.fileName,
      detail: `${p.columns} columns`,
      cycle: 0,
      rowsAddedLastCycle: 0,
      created_at: p.created_at,
      updated_at: p.updated_at,
      liveEnabled: false,
      path: `/app/f/${p.id}`,
    }))
    return [...web, ...files]
  }, [list, local, snaps])

  const setSnap = (id: string, snap: LiveSnapshot) => {
    changedAt.current[id] = Date.now()
    setSnaps((p) => ({ ...p, [id]: snap }))
  }

  return { projects, loading, setSnap }
}
