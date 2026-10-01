import { apiDate } from '../../api/dates.ts'

type Dated = { updated_at: string }
export type HistoryGroup<T extends Dated> = { label: string; items: T[] }

const LABELS = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Older'] as const

/** ChatGPT-style history buckets by last update, in local days. Empty buckets are left out. */
export function groupByDay<T extends Dated>(list: T[], now = new Date()): HistoryGroup<T>[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const DAY = 86_400_000
  const buckets = LABELS.map((label) => ({ label, items: [] as T[] }))
  for (const item of list) {
    const t = apiDate(item.updated_at)?.getTime() ?? 0
    const index =
      t >= startOfToday ? 0 : t >= startOfToday - DAY ? 1 : t >= startOfToday - 7 * DAY ? 2 : t >= startOfToday - 30 * DAY ? 3 : 4
    buckets[index].items.push(item)
  }
  return buckets.filter((b) => b.items.length > 0)
}

/** The backend names an untouched instance "New track", "Untitled chat", or "New session". */
export const isUntitled = (title: string) => {
  const t = title.trim()
  return !t || t === 'New track' || t === 'Untitled chat' || t === 'New session'
}
