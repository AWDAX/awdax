import { mergeStreamedRows } from './mergeRows.ts'
import type { DatasetTable, StreamedRows } from './types.ts'

/**
 * Orders an HTTP snapshot against live `rows` frames. Frames that arrive while a snapshot is in flight
 * are kept and replayed onto the snapshot (row ids dedupe), and a snapshot that was overtaken by a newer
 * request, a filter change or a reset is discarded instead of published.
 */
export function createSnapshotGate() {
  let generation = 0
  let loading = false
  let activeKey = ''
  let queue: StreamedRows[] = []

  return {
    /** Start a snapshot for this filter; returns its generation and marks the gate "loading". */
    begin(filterKey: string): number {
      generation += 1
      activeKey = filterKey
      loading = true
      return generation
    },
    isLoading(): boolean {
      return loading
    },
    /** Keep a frame so the next accepted snapshot can replay it. */
    buffer(frame: StreamedRows): void {
      queue.push(frame)
    },
    /** The snapshot with buffered frames replayed, or null when it is stale and must be discarded. */
    finish(gen: number, filterKey: string, table: DatasetTable): DatasetTable | null {
      if (gen !== generation) return null
      loading = false
      if (filterKey !== activeKey) {
        // Frames from before the filter change belong to the old view; the next snapshot starts clean.
        queue = []
        return null
      }
      const queued = queue
      queue = []
      if (queued.length === 0) return table
      let next = table
      for (const frame of queued) next = mergeStreamedRows(next, frame)
      // A frame older than the snapshot carries an older total; never let replay shrink the count.
      return { ...next, row_count: Math.max(table.row_count ?? table.rows.length, next.row_count ?? 0) }
    },
    /** A snapshot that failed: stop "loading" (so frames merge or trigger a retry), keep the buffer. */
    settle(gen: number): void {
      if (gen === generation) loading = false
    },
    /** Forget buffered frames, e.g. when a batch's final scoring makes them stale. */
    dropBuffer(): void {
      queue = []
    },
    /** Drop the buffer and invalidate any in-flight snapshot (run reset, 404, unmount). */
    reset(): void {
      generation += 1
      loading = false
      queue = []
    },
  }
}
