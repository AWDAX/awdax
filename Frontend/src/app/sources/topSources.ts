import type { SourceView } from './buildSources.ts'

/** Most useful first: the site being read now, then by rows given, rejected sites last; ties keep their order. */
export function topSources(sources: SourceView[]): SourceView[] {
  const rank = (s: SourceView) => (s.state === 'reading' ? 0 : s.state === 'rejected' ? 2 : 1)
  return sources
    .map((s, i) => ({ s, i }))
    .sort((a, b) => rank(a.s) - rank(b.s) || b.s.rows - a.s.rows || a.i - b.i)
    .map(({ s }) => s)
}
