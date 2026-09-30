import type { SampleRun } from '../../domain/fixtures/index.ts'
import type { SourceStage } from '../../domain/types.ts'
import { planItemCount } from '../../product/planItems.ts'

/**
 * The hero's sample run as a pure function of elapsed time: frameAt(t) says what is on screen
 * at t milliseconds. Pausing stops the clock; reduced motion jumps straight to the end.
 */

export type Phase = 'ask' | 'plan' | 'run' | 'review' | 'use'

export const PHASES: Phase[] = ['ask', 'plan', 'run', 'review', 'use']

/** The first rows are read slowly, one source page at a time, so the trace from page to cell can be seen. */
export const DETAILED_ROWS = 3

const MS = {
  lead: 700,
  char: 30,
  think: 700,
  planItem: 130,
  approveHold: 1300,
  press: 260,
  runDelay: 500,
  firstRow: 350,
  /**
   * A detailed row: its page opens, the values highlight, then the row lands. The rest of the step
   * holds the page while TraceLayer draws (450ms wait + 1000ms draw + 2 × 160ms stagger = 1770ms),
   * then leaves the finished lines up for a beat (about 630ms) before the next page.
   */
  read: 1400,
  detailedRow: 3800,
  row: 380,
  review: 2200,
}

export interface Schedule {
  typeEnd: number
  planStart: number
  planEnd: number
  pressAt: number
  approveAt: number
  runStart: number
  /** When each detailed row's source page opens. */
  readAt: number[]
  rowAt: number[]
  reviewAt: number
  useAt: number
}

export function scheduleFor(s: SampleRun): Schedule {
  const typeEnd = MS.lead + s.request.text.length * MS.char
  const planStart = typeEnd + MS.think
  const planEnd = planStart + planItemCount(s.plan, 'compact') * MS.planItem
  const pressAt = planEnd + MS.approveHold
  const approveAt = pressAt + MS.press
  const runStart = approveAt + MS.runDelay
  const readAt: number[] = []
  const rowAt: number[] = []
  let cursor = runStart + MS.firstRow
  s.dataset.rows.forEach((_, i) => {
    if (i < DETAILED_ROWS) {
      readAt.push(cursor)
      rowAt.push(cursor + MS.read)
      cursor += MS.detailedRow
    } else {
      rowAt.push(cursor)
      cursor += MS.row
    }
  })
  const reviewAt = (rowAt[rowAt.length - 1] ?? runStart) + 500
  return { typeEnd, planStart, planEnd, pressAt, approveAt, runStart, readAt, rowAt, reviewAt, useAt: reviewAt + MS.review }
}

export interface Frame {
  phase: Phase
  typed: number
  planRevealed: number
  pressing: boolean
  approved: boolean
  /** Source pages opened so far (detailed rows only). */
  reading: number
  rowsShown: number
  stages: Partial<Record<string, SourceStage>>
  rowsFound: Partial<Record<string, number>>
  done: boolean
}

export function frameAt(s: SampleRun, sch: Schedule, t: number): Frame {
  const text = s.request.text
  const typed = Math.max(0, Math.min(text.length, Math.floor((t - MS.lead) / MS.char)))
  const planRevealed = t < sch.planStart ? 0 : Math.floor((t - sch.planStart) / MS.planItem) + 1
  const approved = t >= sch.approveAt
  const reading = sch.readAt.filter((at) => t >= at).length
  const rowsShown = sch.rowAt.filter((at) => t >= at).length
  const shownRows = s.dataset.rows.slice(0, rowsShown)

  const stages: Frame['stages'] = {}
  const rowsFound: Frame['rowsFound'] = {}
  if (approved) {
    for (const src of s.plan.sources) {
      const mine = s.dataset.rows.filter((r) => r.sourceIds[0] === src.id)
      const got = shownRows.filter((r) => r.sourceIds[0] === src.id).length
      rowsFound[src.id] = got
      stages[src.id] =
        src.permission !== 'allowed'
          ? t >= sch.runStart
            ? 'skipped'
            : 'queued'
          : t < sch.runStart
            ? 'queued'
            : got === mine.length
              ? 'done'
              : got === 0
                ? 'fetching'
                : 'extracting'
    }
  }

  const phase: Phase =
    t < sch.planStart ? 'ask' : !approved ? 'plan' : t < sch.reviewAt ? 'run' : t < sch.useAt ? 'review' : 'use'

  return {
    phase,
    typed,
    planRevealed,
    pressing: t >= sch.pressAt && !approved,
    approved,
    reading,
    rowsShown,
    stages,
    rowsFound,
    done: t >= sch.useAt,
  }
}

/** Frames that would render the same. Lets the clock tick every animation frame without re-rendering on each. */
export function sameFrame(a: Frame, b: Frame): boolean {
  return (
    a.phase === b.phase &&
    a.typed === b.typed &&
    a.planRevealed === b.planRevealed &&
    a.pressing === b.pressing &&
    a.approved === b.approved &&
    a.reading === b.reading &&
    a.rowsShown === b.rowsShown &&
    JSON.stringify(a.stages) === JSON.stringify(b.stages)
  )
}
