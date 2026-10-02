import type { LivePhase, LiveStatus } from '../../api/types.ts'

/** The backend's pipeline steps in order; runTrace.ts turns them into the run line's trace. */
export const STEPS: { phase: LivePhase }[] = [{ phase: 'discovery' }, { phase: 'inspect' }, { phase: 'extract' }, { phase: 'merge' }]

export const WORKING: LivePhase[] = ['discovery', 'inspect', 'extract', 'merge']

const LABEL: Record<LivePhase, string> = {
  idle: 'Waiting to start',
  discovery: 'Finding sources…',
  inspect: 'Reading the pages…',
  extract: 'Pulling rows…',
  merge: 'Merging new rows…',
  sleep: 'Up to date',
  error: 'Stopped on an error',
  stopped: 'Tracking paused',
}

export function phaseLabel(s: Partial<LiveStatus>, liveEnabled: boolean): string {
  if (!liveEnabled) return LABEL.stopped
  if (s.lane === 'deep') return 'Interactive pass…'
  if (s.lane === 'dataset') return 'Reading a linked dataset…'
  return LABEL[s.phase ?? 'idle'] ?? LABEL.idle
}
