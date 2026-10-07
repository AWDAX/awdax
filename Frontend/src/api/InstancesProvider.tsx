import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { adoptLegacyAlerts } from '../app/chat/alerts.ts'
import { adoptUnscopedKeys, CHAT_KEY_PREFIXES } from '../app/auth/userScope.ts'
import { awdax } from './awdax.ts'
import { forgetChatTitle, migrateLocalTitlesToBackend } from './chatTitles.ts'
import { apiTime } from './dates.ts'
import { createListSequence } from './listSequence.ts'
import { InstancesContext } from './instancesContext.ts'
import type { Instances } from './instancesContext.ts'
import { notifyInstancesChanged, subscribeInstancesChanged } from './instancesSync.ts'
import type { InstanceSummary } from './types.ts'

const REFRESH_MS = 30_000

const byUpdated = (a: InstanceSummary, b: InstanceSummary) => apiTime(b.updated_at) - apiTime(a.updated_at)

/**
 * The chat list for the sidebar, history and projects report. Loads from the backend, refreshes on focus,
 * on a short interval, and immediately when any tab creates, renames, or deletes an instance.
 */
export function InstancesProvider({ children }: { children: ReactNode }) {
  const [list, setList] = useState<InstanceSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [listOk, setListOk] = useState(false)
  const migrated = useRef(false)
  const seq = useRef(createListSequence())

  const refresh = useCallback(async () => {
    const token = seq.current.begin()
    try {
      const next = await awdax.listInstances()
      if (!seq.current.accept(token)) return
      setList(next)
      setError(null)
      setListOk(true)
    } catch (err) {
      if (!seq.current.accept(token)) return
      setError(err instanceof Error ? err.message : 'Could not load chats')
      setListOk(false)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const first = window.setTimeout(refresh, 0)
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'hidden') void refresh()
    }, REFRESH_MS)
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
    // Only once the backend has said which chats are this account's: browser data saved before it was per account
    // is adopted for those chats alone, and a stored title is sent only for a chat this account owns.
    if (migrated.current || loading || !listOk) return
    migrated.current = true
    const owned = new Set(list.map((i) => i.id))
    adoptUnscopedKeys(CHAT_KEY_PREFIXES, owned)
    adoptLegacyAlerts(owned)
    void migrateLocalTitlesToBackend(async (id, title) => {
      const summary = await awdax.updateInstance(id, { title })
      seq.current.mutated()
      setList((prev) => [summary, ...prev.filter((i) => i.id !== id)].sort(byUpdated))
    }, owned).then(() => notifyInstancesChanged('mutate'))
  }, [loading, listOk, list])

  const upsert = useCallback((item: InstanceSummary) => {
    const summary: InstanceSummary = {
      id: item.id,
      title: item.title,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
    seq.current.mutated()
    setList((prev) => [summary, ...prev.filter((i) => i.id !== item.id)].sort(byUpdated))
  }, [])

  const remove = useCallback(async (id: string) => {
    await awdax.deleteInstance(id)
    forgetChatTitle(id)
    seq.current.mutated()
    setList((prev) => prev.filter((i) => i.id !== id))
    notifyInstancesChanged('delete')
  }, [])

  const rename = useCallback(async (id: string, title: string) => {
    const trimmed = title.trim()
    if (!trimmed) return
    const summary = await awdax.updateInstance(id, { title: trimmed })
    forgetChatTitle(id)
    seq.current.mutated()
    setList((prev) => [summary, ...prev.filter((i) => i.id !== id)].sort(byUpdated))
    notifyInstancesChanged('rename')
  }, [])

  const value = useMemo<Instances>(
    () => ({ list, loading, error, listOk, refresh, upsert, remove, rename }),
    [list, loading, error, listOk, refresh, upsert, remove, rename],
  )

  return <InstancesContext.Provider value={value}>{children}</InstancesContext.Provider>
}
