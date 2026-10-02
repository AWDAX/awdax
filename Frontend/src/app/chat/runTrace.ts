import type { LivePhase, LiveStatus } from '../../api/types.ts'
import { STEPS } from './phases.ts'

const NOW: Partial<Record<LivePhase, string>> = { discovery: 'Finding sources', inspect: 'Reading pages', extract: 'Pulling rows', merge: 'Merging rows' }
const DONE: Partial<Record<LivePhase, string>> = { discovery: 'Found sources', inspect: 'Read the pages', extract: 'Pulled rows', merge: 'Merged rows' }

/**
 * The run as ThoughtLine's trace: the pipeline steps reached so far (earlier ones ticked, the current one naming
 * the site it is on), every step ticked once rows are in, nothing on an error or a paused run with no rows.
 * `waiting` is a new run that has not reported a step yet.
 */
export function runTrace(s: Partial<LiveStatus>, liveEnabled: boolean, hasData: boolean, site?: string) {
  const phase = s.phase ?? 'idle'
  const at = STEPS.findIndex((x) => x.phase === phase)
  if (liveEnabled && at >= 0) {
    const steps = STEPS.slice(0, at + 1).map((x, i) => (i < at ? DONE[x.phase]! : `${NOW[x.phase]}${site ? ` · ${site}` : ''}`))
    return { busy: true, steps, waiting: false }
  }
  if (hasData && phase !== 'error') return { busy: false, steps: STEPS.map((x) => DONE[x.phase]!), waiting: false }
  return { busy: false, steps: [] as string[], waiting: liveEnabled && phase === 'idle' }
}
