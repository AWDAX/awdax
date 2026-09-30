/**
 * The shared vocabulary of AWDAX, and the data contract with the backend.
 * docs/PRODUCT.md, "Core objects", is the plain-English version of this file.
 *
 * Rules the backend and frontend both hold to:
 * - Dates are ISO 8601 strings in UTC.
 * - A value that was not found is `null` with status 'not_found'. It is never guessed.
 * - Every found value carries its receipt: sourceUrl, capturedAt, quote and method.
 */

export type ISODate = string

// ── Request and plan ────────────────────────────────────────────────────

export interface Request {
  id: string
  text: string
  createdAt: ISODate
}

/** Drives formatting, validation and which chart a column gets. */
export type ColumnType = 'text' | 'number' | 'money' | 'date' | 'url' | 'category' | 'location' | 'list' | 'boolean'

export interface Column {
  key: string
  label: string
  type: ColumnType
  required: boolean
  /** ISO 4217 code for 'money' columns, e.g. 'INR'. */
  currency?: string
  /** For a 'category' column whose values have an order (tiers, sizes): highest first. */
  levels?: string[]
}

export type FilterOp = 'eq' | 'in' | 'contains' | 'gte' | 'lte' | 'between' | 'within_days'

export interface Filter {
  column: string
  op: FilterOp
  value: string | number | string[] | [number, number]
  /** How the filter reads to a person, e.g. "Posted in the last 14 days". */
  label: string
}

/** How an unclear word in the request was read, with the other readings on offer. */
export interface Interpretation {
  phrase: string
  readAs: string
  alternatives: string[]
}

/** How a value was collected, cheapest first. Each has its own color in the UI. */
export type Method = 'structured' | 'content' | 'rendered' | 'ai'

export type Permission = 'allowed' | 'robots_disallowed' | 'needs_login' | 'rate_limited'

export interface Source {
  id: string
  name: string
  domain: string
  permission: Permission
  /** The method AWDAX expects to use; each value records the one it actually used. */
  method: Method
  health: 'ok' | 'slow' | 'failing' | 'unknown'
  /** Why the source is skipped, when permission is not 'allowed'. */
  note?: string
}

export interface Plan {
  id: string
  requestId: string
  columns: Column[]
  filters: Filter[]
  sources: Source[]
  interpretations: Interpretation[]
  rowLimit: number
  /** Null until the user approves. Nothing runs before that. */
  approvedAt: ISODate | null
}

// ── Run ─────────────────────────────────────────────────────────────────

export type RunStatus = 'queued' | 'running' | 'paused' | 'cancelled' | 'done' | 'failed'

export type SourceStage = 'queued' | 'fetching' | 'extracting' | 'done' | 'skipped' | 'failed'

export interface SourceProgress {
  sourceId: string
  stage: SourceStage
  pagesFetched: number
  rowsFound: number
  /** Plain-language reason, shown when stage is 'skipped' or 'failed'. */
  reason?: string
}

export type RunEventKind = 'stage' | 'rows' | 'skip' | 'retry' | 'error' | 'info'

/** One line of the activity log. The backend streams these (server-sent events assumed). */
export interface RunEvent {
  id: string
  runId: string
  at: ISODate
  kind: RunEventKind
  sourceId?: string
  stage?: SourceStage
  rows?: number
  message: string
}

export interface Run {
  id: string
  planId: string
  status: RunStatus
  startedAt: ISODate
  finishedAt: ISODate | null
  progress: SourceProgress[]
  events: RunEvent[]
}

// ── Dataset ─────────────────────────────────────────────────────────────

export type CellValue = string | number | boolean | string[]

export type Confidence = 'high' | 'medium' | 'low'

export type CellStatus = 'found' | 'not_found' | 'conflict'

/** Another value a different source gave for the same cell. */
export interface CellAlternative {
  value: CellValue
  sourceUrl: string
  capturedAt: ISODate
  quote: string
}

export interface Cell {
  /** Null only when status is 'not_found'. */
  value: CellValue | null
  status: CellStatus
  sourceUrl: string | null
  capturedAt: ISODate | null
  /** The exact text on the source page the value was read from. */
  quote: string | null
  confidence: Confidence | null
  method: Method | null
  /** Present when status is 'conflict'. `value` holds the one chosen by rule. */
  alternatives?: CellAlternative[]
}

export interface Row {
  id: string
  cells: Record<string, Cell>
  /** Every source this row was found on, after duplicates were merged. */
  sourceIds: string[]
}

export interface MergeGroup {
  keptRowId: string
  mergedCount: number
  /** What made them the same row, e.g. "Same company and website". */
  matchedOn: string
}

export interface RejectedRow {
  sourceId: string
  label: string
  reason: string
}

export interface CleaningReport {
  rawRows: number
  uniqueRows: number
  merged: MergeGroup[]
  rejected: RejectedRow[]
  /** Row ids that contain at least one cell with status 'conflict'. */
  conflictRowIds: string[]
}

export interface Dataset {
  id: string
  runId: string
  version: number
  createdAt: ISODate
  columns: Column[]
  rows: Row[]
  cleaning: CleaningReport
}

// ── Monitor ─────────────────────────────────────────────────────────────

export interface Change {
  kind: 'added' | 'removed' | 'changed'
  rowId: string
  column?: string
  before?: CellValue | null
  after?: CellValue | null
}

export interface Monitor {
  id: string
  planId: string
  schedule: { every: 'day' | 'week'; atUtc: string }
  lastRunAt: ISODate | null
  nextRunAt: ISODate
  lastDatasetVersion: number
  changes: Change[]
}
