import { useEffect, useState } from 'react'
import { listLocal, onLocalChange } from './localProjects.ts'
import type { LocalMeta } from './localProjects.ts'

/** Uploaded-file projects in this browser, kept current when one is added or deleted. */
export function useLocalProjects(): LocalMeta[] {
  const [list, setList] = useState<LocalMeta[]>([])
  useEffect(() => {
    let alive = true
    const load = () =>
      listLocal()
        .then((l) => alive && setList(l))
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
