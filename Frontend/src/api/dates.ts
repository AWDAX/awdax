/**
 * The backend stores times in UTC but SQLite drops the offset, so instance and message times arrive as
 * '2026-09-27T16:28:02.728883' with no 'Z'. `new Date()` would read that as local time (5h30 off in
 * India). Live status times do carry '+00:00'. This reads both correctly.
 */
export function apiDate(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const d = new Date(/(?:[zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Milliseconds since the epoch, or 0 when missing: for sorting. */
export const apiTime = (iso: string | null | undefined) => apiDate(iso)?.getTime() ?? 0

const MIN = 60_000
const HOUR = 60 * MIN
const DAY = 24 * HOUR

/** "just now", "4 min ago", "3 h ago", "2 days ago", then a date like "14 Sep 2026". */
export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  const d = apiDate(iso)
  if (!d) return '—'
  const diff = now - d.getTime()
  if (diff < MIN) return 'just now'
  if (diff < HOUR) return `${Math.floor(diff / MIN)} min ago`
  if (diff < DAY) return `${Math.floor(diff / HOUR)} h ago`
  if (diff < 7 * DAY) {
    const days = Math.floor(diff / DAY)
    return days === 1 ? 'yesterday' : `${days} days ago`
  }
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
