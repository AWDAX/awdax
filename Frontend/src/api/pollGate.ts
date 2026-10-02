import { WORKING } from '../app/chat/phases.ts'
import type { LivePhase } from './types.ts'

/** A run is doing work, so rows may arrive. Paused tracking still counts while a pass is running:
 * the pass finishes and its rows land. */
export function isRunActive(phase: LivePhase | undefined): boolean {
  return !!phase && WORKING.includes(phase)
}

/** Whether a 5 s poll tick should fetch: only a visible tab with an active run can see anything new. */
export function shouldPoll(visible: boolean, phase: LivePhase | undefined): boolean {
  return visible && isRunActive(phase)
}

/** A run started or finished. Either way the table should be fetched now: at the start so rows show
 * without waiting for a tick, at the end because the server re-merges and re-scores the final table
 * and the event stream does not announce that. */
export function runActivityChanged(before: LivePhase | undefined, after: LivePhase | undefined): boolean {
  return isRunActive(before) !== isRunActive(after)
}
