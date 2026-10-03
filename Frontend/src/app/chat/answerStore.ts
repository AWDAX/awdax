import { AGG_LABEL, columnsExist, filterColumnsExist } from '../../analytics/aggregate.ts'
import type { Query } from '../../analytics/aggregate.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import type { ChartType } from '../../analytics/spec.ts'
import type { Intent } from '../../analytics/suggest.ts'

/**
 * Questions asked about one chat's data, kept in this browser. A query answer stores only the question and its
 * query; the numbers are recomputed from the current table every time, so it never goes stale. A computed
 * answer (heavier maths, run on the server) stores its result table, a snapshot of the rows it was given.
 */
interface AnswerBase {
  id: string
  question: string
  createdAt: string
  /** The table's columns when the question was asked; the query's column numbers only mean something while it holds. */
  signature?: string
}

export interface QueryAnswer extends AnswerBase {
  intent: Intent
  chart: ChartType
  query: Query
  computed?: undefined
}

/** A calculation's result: its schema (column names and types), its rows, and what it means in one sentence. */
export interface ComputedResult {
  columns: { name: string; type: string }[]
  rows: (string | number | null)[][]
  meaning: string
  /** Rows in the table it was computed from. */
  basis: number
}

export interface ComputedAnswer extends AnswerBase {
  computed: ComputedResult
}

export type SavedAnswer = QueryAnswer | ComputedAnswer

type Fresh<T> = T extends unknown ? Omit<T, 'id' | 'createdAt' | 'signature'> : never
export type NewAnswer = Fresh<SavedAnswer>

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
export function isStaleAnswer(a: QueryAnswer, profile: TableProfile): boolean {
  if (a.signature !== undefined && a.signature !== columnSignature(profile)) return true
  return !isQuery(a.query) || !columnsExist(profile, a.query) || !filterColumnsExist(profile, a.query.filters)
}

/** Reads the stored list. Entries without an id and a question can't be shown or removed, so they are skipped. */
export function parseAnswers(raw: string | null): SavedAnswer[] {
  try {
    const v: unknown = JSON.parse(raw ?? '[]')
    if (!Array.isArray(v)) return []
    return v.filter(
      (x): x is SavedAnswer =>
        typeof x === 'object' && x !== null && typeof x.id === 'string' && typeof x.question === 'string' &&
        // A computed answer must carry a whole table, or there is nothing to show.
        (x.computed === undefined || (Array.isArray(x.computed.columns) && Array.isArray(x.computed.rows))),
    )
  } catch {
    return []
  }
}
