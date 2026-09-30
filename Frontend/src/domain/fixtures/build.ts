import type {
  Cell,
  CellValue,
  Column,
  Confidence,
  Dataset,
  Filter,
  Interpretation,
  MergeGroup,
  Method,
  Plan,
  RejectedRow,
  Request,
  Row,
  Source,
} from '../types.ts'

/**
 * Sample runs: fictional entities on reserved `.example` domains, so nothing here
 * can be mistaken for a real company's data. Every place they appear is labeled "sample run".
 */

export type SampleKey = 'jobs' | 'leads' | 'sponsors' | 'market'

export interface SampleRun {
  key: SampleKey
  /** Preset button label. */
  label: string
  request: Request
  plan: Plan
  dataset: Dataset
  /** Columns the compact row stream shows, in order. */
  streamColumns: [string, string, string]
  /** Column the hero chart is drawn from. */
  heroChart: string
}

/** null = not found on any source. Otherwise [value, quote, confidence?, method?]. */
export type FieldSpec = null | [value: CellValue, quote: string, confidence?: Confidence, method?: Method]

export interface RowSpec {
  src: string
  path: string
  fields: Record<string, FieldSpec>
  /** Other sources the same row was found on; they were merged into this one. */
  also?: string[]
  /** A different value another source gave. The row's own value was chosen by rule. */
  conflicts?: Record<string, { src: string; path: string; value: CellValue; quote: string }>
}

interface SampleInput {
  key: SampleKey
  label: string
  text: string
  columns: Column[]
  filters: Filter[]
  interpretations: Interpretation[]
  sources: Source[]
  rowLimit: number
  rows: RowSpec[]
  rejected: RejectedRow[]
  /** Why merged rows count as the same row, e.g. "Same title and company". */
  matchedOn: string
  streamColumns: [string, string, string]
  heroChart: string
}

// Every sample run starts at the same moment; capture times count up from it.
const RUN_START = Date.parse('2026-09-27T04:30:00Z')
const at = (seconds: number) => new Date(RUN_START + seconds * 1000).toISOString()

const MISSING: Cell = {
  value: null,
  status: 'not_found',
  sourceUrl: null,
  capturedAt: null,
  quote: null,
  confidence: null,
  method: null,
}

function sourceOf(sources: Source[], id: string): Source {
  const s = sources.find((x) => x.id === id)
  if (!s) throw new Error(`Sample row points at unknown source "${id}"`)
  return s
}

const urlOf = (sources: Source[], id: string, path: string) => `https://${sourceOf(sources, id).domain}${path}`

function buildRow(input: SampleInput, spec: RowSpec, i: number): Row {
  const src = sourceOf(input.sources, spec.src)
  const sourceUrl = urlOf(input.sources, spec.src, spec.path)
  const capturedAt = at(20 + i * 11)
  const cells: Record<string, Cell> = {}

  for (const col of input.columns) {
    const field = spec.fields[col.key]
    if (field === undefined) throw new Error(`Sample row ${i + 1} of "${input.key}" is missing column "${col.key}"`)
    if (field === null) {
      cells[col.key] = MISSING
      continue
    }
    const [value, quote, confidence = 'high', method = src.method] = field
    const conflict = spec.conflicts?.[col.key]
    cells[col.key] = {
      value,
      status: conflict ? 'conflict' : 'found',
      sourceUrl,
      capturedAt,
      quote,
      confidence,
      method,
      ...(conflict && {
        alternatives: [
          {
            value: conflict.value,
            sourceUrl: urlOf(input.sources, conflict.src, conflict.path),
            capturedAt: at(26 + i * 11),
            quote: conflict.quote,
          },
        ],
      }),
    }
  }

  const conflictSources = Object.values(spec.conflicts ?? {}).map((c) => c.src)
  const sourceIds = [...new Set([spec.src, ...(spec.also ?? []), ...conflictSources])]
  return { id: `${input.key}-${String(i + 1).padStart(2, '0')}`, cells, sourceIds }
}

export function defineSample(input: SampleInput): SampleRun {
  for (const key of [...input.streamColumns, input.heroChart]) {
    if (!input.columns.some((c) => c.key === key)) throw new Error(`Sample "${input.key}" refers to unknown column "${key}"`)
  }
  const rows = input.rows.map((spec, i) => buildRow(input, spec, i))

  const merged: MergeGroup[] = rows
    .filter((r) => r.sourceIds.length > 1)
    .map((r) => ({ keptRowId: r.id, mergedCount: r.sourceIds.length, matchedOn: input.matchedOn }))

  // Raw rows = every row any source returned: the unique ones, the duplicates merged
  // into them, and the ones that failed checks.
  const duplicates = merged.reduce((n, g) => n + g.mergedCount - 1, 0)
  const conflictRowIds = rows
    .filter((r) => Object.values(r.cells).some((c) => c.status === 'conflict'))
    .map((r) => r.id)

  const requestId = `req-${input.key}`
  const planId = `plan-${input.key}`
  const runId = `run-${input.key}`

  return {
    key: input.key,
    label: input.label,
    request: { id: requestId, text: input.text, createdAt: at(0) },
    plan: {
      id: planId,
      requestId,
      columns: input.columns,
      filters: input.filters,
      sources: input.sources,
      interpretations: input.interpretations,
      rowLimit: input.rowLimit,
      approvedAt: at(8),
    },
    dataset: {
      id: `ds-${input.key}`,
      runId,
      version: 1,
      createdAt: at(20 + rows.length * 11 + 15),
      columns: input.columns,
      rows,
      cleaning: {
        rawRows: rows.length + duplicates + input.rejected.length,
        uniqueRows: rows.length,
        merged,
        rejected: input.rejected,
        conflictRowIds,
      },
    },
    streamColumns: input.streamColumns,
    heroChart: input.heroChart,
  }
}
