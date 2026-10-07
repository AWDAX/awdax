import { useEffect, useState } from 'react'
import { adoptUnscopedKeys, CHAT_KEY_PREFIXES } from '../auth/userScope.ts'
import { listLocal, onLocalChange } from './localProjects.ts'
import type { LocalMeta } from './localProjects.ts'

/** Uploaded-file projects in this browser, kept current when one is added or deleted. */
export function useLocalProjects(): LocalMeta[] {
  const [list, setList] = useState<LocalMeta[]>([])
  useEffect(() => {
    let alive = true
    const load = () =>
      listLocal()
        .then((l) => {
          if (!alive) return
          // Saved answers/dashboards of these uploaded files predate per-account keys: they are this account's.
          adoptUnscopedKeys(CHAT_KEY_PREFIXES, l.map((p) => `file-${p.id}`))
          setList(l)
        })
        .catch(() => undefined)
    void load()
    const off = onLocalChange(() => void load())
    return () => {
      alive = false
      off()
    }
  }, [])
  return list
}
