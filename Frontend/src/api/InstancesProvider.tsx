import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { awdax } from './awdax.ts'
import { forgetChatTitle, migrateLocalTitlesToBackend } from './chatTitles.ts'
import { apiTime } from './dates.ts'
import { InstancesContext } from './instancesContext.ts'
import type { Instances } from './instancesContext.ts'
import { notifyInstancesChanged, subscribeInstancesChanged } from './instancesSync.ts'
import type { InstanceSummary } from './types.ts'

const REFRESH_MS = 5_000

const byUpdated = (a: InstanceSummary, b: InstanceSummary) => apiTime(b.updated_at) - apiTime(a.updated_at)

/**
 * The chat list for the sidebar, history and projects report. Loads from the backend, refreshes on focus,
 * on a short interval, and immediately when any tab creates, renames, or deletes an instance.
 */
export function InstancesProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<InstanceSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const migrated = useRef(false)

  const refresh = useCallback(async () => {
    try {
      const next = await awdax.listInstances()
      setList(next)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load chats')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const first = window.setTimeout(refresh, 0)
    const timer = window.setInterval(refresh, REFRESH_MS)
    const onFocus = () => void refresh()
    window.addEventListener('focus', onFocus)
    const stopSync = subscribeInstancesChanged(() => void refresh())
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
      window.removeEventListener('focus', onFocus)
      stopSync()
    }
  }, [refresh])

  useEffect(() => {
    if (migrated.current || loading) return
    migrated.current = true
    void migrateLocalTitlesToBackend(async (id, title) => {
      const summary = await awdax.updateInstance(id, { title })
      setList((prev) => [summary, ...prev.filter((i) => i.id !== id)].sort(byUpdated))
    }).then(() => notifyInstancesChanged('mutate'))
  }, [loading])

  const upsert = useCallback((item: InstanceSummary) => {
    const summary: InstanceSummary = {
      id: item.id,
      title: item.title,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
    setList((prev) => [summary, ...prev.filter((i) => i.id !== item.id)].sort(byUpdated))
  }, [])

  const remove = useCallback(async (id: string) => {
    await awdax.deleteInstance(id)
    forgetChatTitle(id)
    setList((prev) => prev.filter((i) => i.id !== id))
    notifyInstancesChanged('delete')
  }, [])

  const rename = useCallback(async (id: string, title: string) => {
    const trimmed = title.trim()
    if (!trimmed) return
    const summary = await awdax.updateInstance(id, { title: trimmed })
    forgetChatTitle(id)
    setList((prev) => [summary, ...prev.filter((i) => i.id !== id)].sort(byUpdated))
    notifyInstancesChanged('rename')
  }, [])

  const value = useMemo<Instances>(
    () => ({ list, loading, error, refresh, upsert, remove, rename }),
    [list, loading, error, refresh, upsert, remove, rename],
  )

  return <InstancesContext.Provider value={value}>{children}</InstancesContext.Provider>
}
