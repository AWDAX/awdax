import { useMemo } from 'react'
import { apiTime } from '../../api/dates.ts'
import { useInstances } from '../../api/instancesContext.ts'
import { useLocalProjects } from '../files/useLocalProjects.ts'
import { groupByDay } from './groupByDay.ts'
import { HistoryItem } from './HistoryItem.tsx'
import type { Entry } from './HistoryItem.tsx'

/** Every chat ever started, web and file, grouped by day and filtered by the sidebar search. */
export function HistoryList({ query, onNavigate }: { query: string; onNavigate?: () => void }) {
  const { list, loading, error } = useInstances()
  const local = useLocalProjects()
  const q = query.trim().toLowerCase()
  const groups = useMemo(() => {
    const all: Entry[] = [
      ...list.map((i) => ({ id: i.id, title: i.title, updated_at: i.updated_at, kind: 'web' as const })),
      ...local.map((p) => ({ id: p.id, title: p.title, updated_at: p.updated_at, kind: 'file' as const })),
    ].sort((a, b) => apiTime(b.updated_at) - apiTime(a.updated_at))
    return groupByDay(q ? all.filter((i) => i.title.toLowerCase().includes(q)) : all)
  }, [list, local, q])

  if (loading && local.length === 0) {
    return (
      <ul className="flex flex-col gap-2 px-3" aria-label="Loading chats">
        {[0, 1, 2, 3].map((i) => (
          <li key={i} className="h-8 animate-pulse rounded-control bg-sunken" />
        ))}
      </ul>
    )
  }
  if (groups.length === 0) {
    return (
      <p className="px-4 text-small text-ink-3">
        {error && list.length === 0 ? error : q ? `No chats match “${query.trim()}”.` : 'No chats yet. Ask for some data to start one.'}
      </p>
    )
  }

  return (
    <nav aria-label="Chat history" className="flex flex-col gap-5">
      {error && <p className="px-4 text-micro text-blocked">{error}</p>}
      {groups.map((g) => (
        <section key={g.label}>
          <h2 className="px-4 pb-1.5 font-mono text-micro text-ink-3">{g.label}</h2>
          <ul className="flex flex-col px-2">
            {g.items.map((item) => (
              <HistoryItem key={`${item.kind}-${item.id}`} item={item} onNavigate={onNavigate} />
            ))}
          </ul>
        </section>
      ))}
    </nav>
  )
}
