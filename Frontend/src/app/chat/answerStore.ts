import { AGG_LABEL, columnsExist, filterColumnsExist } from '../../analytics/aggregate.ts'
import type { Query } from '../../analytics/aggregate.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import type { ChartType } from '../../analytics/spec.ts'
import type { Intent } from '../../analytics/suggest.ts'

/**
 * Questions asked about one chat's data, kept in this browser. Only the question and its query are stored;
 * the numbers are recomputed from the current table every time, so an answer never goes stale.
 */
export interface SavedAnswer {
  id: string
  question: string
  intent: Intent
  chart: ChartType
  query: Query
  createdAt: string
  /** The table's columns when the question was asked; the query's column numbers only mean something while it holds. */
  signature?: string
}

export type NewAnswer = Omit<SavedAnswer, 'id' | 'createdAt' | 'signature'>

export function newAnswer(a: NewAnswer, signature: string): SavedAnswer {
  return { ...a, id: `q${Date.now().toString(36)}`, createdAt: new Date().toISOString(), signature }
}

const isNum = (v: unknown) => v === undefined || typeof v === 'number'

function isQuery(q: unknown): q is Query {
  if (typeof q !== 'object' || q === null) return false
  const { agg, groupBy, measure, filters } = q as Record<string, unknown>
  if (typeof agg !== 'string' || !(agg in AGG_LABEL) || !isNum(groupBy) || !isNum(measure)) return false
  if (filters === undefined) return true
  return (
    Array.isArray(filters) &&
    filters.every((f) => typeof f === 'object' && f !== null && typeof f.column === 'number' && typeof f.op === 'string' && Array.isArray(f.values))
  )
}

/**
 * True when the answer can't be run against this table: its columns changed since it was asked, or a column
 * it names isn't there. Answers saved before signatures existed have none, so only their column numbers are checked.
 */
export function isStaleAnswer(a: SavedAnswer, profile: TableProfile): boolean {
  if (a.signature !== undefined && a.signature !== columnSignature(profile)) return true
  return !isQuery(a.query) || !columnsExist(profile, a.query) || !filterColumnsExist(profile, a.query.filters)
}

/** Reads the stored list. Entries without an id and a question can't be shown or removed, so they are skipped. */
export function parseAnswers(raw: string | null): SavedAnswer[] {
  try {
    const v: unknown = JSON.parse(raw ?? '[]')
    if (!Array.isArray(v)) return []
    return v.filter((x): x is SavedAnswer => typeof x === 'object' && x !== null && typeof x.id === 'string' && typeof x.question === 'string')
  } catch {
    return []
  }
}
