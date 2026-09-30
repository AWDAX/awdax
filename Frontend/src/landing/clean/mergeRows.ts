import { sampleByKey } from '../../domain/fixtures/index.ts'
import type { Method } from '../../domain/types.ts'

/**
 * The Sponsors sample, first rows, laid out as the sources returned them (raw) and as AWDAX keeps
 * them (unique). Every number on the section is counted from here.
 */
const { dataset, plan, label } = sampleByKey.sponsors

// Seven unique rows: two merged from two sources, one where the sources disagree on the tier.
const KEPT = [0, 1, 2, 3, 4, 5, 10].map((i) => dataset.rows[i])

export type RawRow = {
  id: string
  sourceId: string
  domain: string
  method: Method
  name: string
  tier: string
  /** The unique row it merged into; absent when it failed a check. */
  into?: string
  /** Why it was set aside. */
  rejected?: string
}

export type UniqueRow = { id: string; name: string; tier: string; sources: string[]; merged: number; conflict?: string }

const source = (id: string) => plan.sources.find((s) => s.id === id)!
const nameOf = (company: unknown, event: unknown) => `${company} · ${event}`

const kept: RawRow[] = KEPT.flatMap((row) =>
  row.sourceIds.map((sid) => {
    const alt = sid !== row.sourceIds[0] ? row.cells.tier.alternatives?.find((a) => a.sourceUrl.includes(source(sid).domain)) : undefined
    return {
      id: `${row.id}-${sid}`,
      sourceId: sid,
      domain: source(sid).domain,
      method: source(sid).method,
      name: nameOf(row.cells.company.value, row.cells.event.value),
      tier: String(alt?.value ?? row.cells.tier.value),
      into: row.id,
    }
  }),
)

const rejected: RawRow[] = dataset.cleaning.rejected.map((r, i) => {
  const [company, event] = r.label.split(' · ')
  return {
    id: `rejected-${i}`,
    sourceId: r.sourceId,
    domain: source(r.sourceId).domain,
    method: source(r.sourceId).method,
    name: nameOf(company, event),
    tier: '',
    rejected: r.reason,
  }
})

// As the sources returned them: grouped by source, in plan order, not by row.
const order = plan.sources.map((s) => s.id)
export const RAW: RawRow[] = [...kept, ...rejected].sort((a, b) => order.indexOf(a.sourceId) - order.indexOf(b.sourceId))

export const UNIQUE: UniqueRow[] = KEPT.map((row) => {
  const alt = row.cells.tier.alternatives?.[0]
  return {
    id: row.id,
    name: nameOf(row.cells.company.value, row.cells.event.value),
    tier: String(row.cells.tier.value),
    sources: row.sourceIds.map((sid) => source(sid).domain),
    merged: row.sourceIds.length,
    conflict: alt ? String(alt.value) : undefined,
  }
})

export const SUMMARY = {
  label,
  raw: RAW.length,
  unique: UNIQUE.length,
  duplicates: kept.length - UNIQUE.length,
  rejected: rejected.length,
  conflicts: UNIQUE.filter((u) => u.conflict).length,
  matchedOn: dataset.cleaning.merged[0]?.matchedOn ?? 'Same company and event',
}
