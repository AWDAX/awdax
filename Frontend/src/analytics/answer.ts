import { runQuery } from './aggregate.ts'
import type { Query, QueryResult } from './aggregate.ts'
import { cmp, div, fromInt, mul, sub } from './decimal.ts'
import type { Dec } from './decimal.ts'
import { formatDec, formatFor, plural } from './format.ts'
import { lc } from './profile.ts'
import type { TableProfile } from './profile.ts'
import type { ChartType } from './spec.ts'
import { measureTitle } from './suggest.ts'
import type { Intent } from './suggest.ts'

/** A question answered from the scraped table: the sentence, the exact numbers behind it, and a chart. */
export interface Answer {
  id: string
  question: string
  intent: Intent
  chart: ChartType
  query: Query
  result: QueryResult
  sentence: string
  createdAt: string
}

const pct = (part: Dec, whole: Dec) => div(mul(part, fromInt(100)), whole, 2)

export const STALE_MESSAGE = 'This answer refers to a column that is no longer in the data.'

export function describe(p: TableProfile, intent: Intent, r: QueryResult): string {
  if (r.stale) return STALE_MESSAGE
  if (r.used === 0) return 'No rows match that question, so there is nothing to count.'
  const q = r.query
  const m = q.measure !== undefined ? p.columns[q.measure] : undefined
  const counting = q.agg === 'count' || q.agg === 'distinct'
  const v = (d: Dec | null) => (counting ? formatDec(d) : formatFor(m, d, r.scale))
  const what = lc(measureTitle(p, q))
  const rows = r.rows.filter((x) => x.value !== null)
  const first = rows[0]
  const last = rows[rows.length - 1]

  if (q.groupBy === undefined || !first) {
    const title = measureTitle(p, q)
    return `${title}: ${v(r.overall)}, across ${plural(r.used, 'row')}.`
  }
  switch (intent) {
    case 'top':
    case 'bottom': {
      const word = intent === 'top' ? 'highest' : 'lowest'
      if ((q.limit ?? 1) > 1) {
        return `${intent === 'top' ? 'Top' : 'Bottom'} ${rows.length} by ${what}: ${rows.map((x) => `${x.label} (${v(x.value)})`).join(', ')}.`
      }
      return `${first.label} has the ${word} ${what}: ${v(first.value)} (${plural(first.count, 'row')}).`
    }
    case 'trend': {
      if (rows.length < 2) return `Only one period has data: ${first.label}, ${v(first.value)}.`
      const change = !counting && first.value && cmp(first.value, fromInt(0)) !== 0 ? pct(sub(last.value!, first.value), first.value) : null
      const peak = rows.reduce((a, b) => (cmp(b.value!, a.value!) > 0 ? b : a))
      const moved = change === null ? '' : `, ${change.n >= 0n ? 'up' : 'down'} ${formatDec(change.n < 0n ? { n: -change.n, s: change.s } : change)}%`
      return `${capital(what)} went from ${v(first.value)} in ${first.label} to ${v(last.value)} in ${last.label}${moved}. The peak was ${peak.label}, at ${v(peak.value)}.`
    }
    case 'share': {
      const total = r.overall
      if (!total || cmp(total, fromInt(0)) === 0) return `${first.label} leads with ${v(first.value)}.`
      return `${first.label} has the largest share: ${formatDec(pct(first.value!, total))}% (${v(first.value)} of ${v(total)}).`
    }
    case 'compare': {
      if (rows.length < 2) return `Only ${first.label} has data: ${v(first.value)}.`
      const [a, b] = rows
      const diff = cmp(b.value!, fromInt(0)) !== 0 ? pct(sub(a.value!, b.value!), b.value!) : null
      const rel = diff === null ? '' : ` ${a.label} is ${formatDec(diff.n < 0n ? { n: -diff.n, s: diff.s } : diff)}% ${diff.n < 0n ? 'lower' : 'higher'}.`
      return `${a.label}: ${v(a.value)} · ${b.label}: ${v(b.value)}.${rel}`
    }
    case 'count':
      return `${first.label} has the most rows (${formatDec(first.value)}), across ${plural(rows.length, 'group')}.`
    case 'average':
      return rows.length > 1
        ? `Highest ${what}: ${first.label}, ${v(first.value)}. Lowest: ${last.label}, ${v(last.value)}.`
        : `${first.label}: ${v(first.value)} (${plural(first.count, 'row')}).`
    default: {
      // "Total revenue by channel": every group (up to 6) and the overall figure, largest first.
      const listed = rows.slice(0, 6).map((x) => `${x.label} ${v(x.value)}`).join(' · ')
      const more = rows.length > 6 ? ` and ${plural(rows.length - 6, 'more group')}` : ''
      return `${capital(what)}: ${listed}${more}. Overall: ${v(r.overall)}.`
    }
  }
}

const capital = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

let seq = 0
export function answer(p: TableProfile, question: string, intent: Intent, query: Query, chart: ChartType): Answer {
  const result = runQuery(p, query)
  return {
    id: `a${Date.now().toString(36)}${(seq++).toString(36)}`,
    question,
    intent,
    chart,
    query,
    result,
    sentence: describe(p, intent, result),
    createdAt: new Date().toISOString(),
  }
}
