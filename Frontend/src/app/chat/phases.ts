import type { LivePhase, LiveStatus } from '../../api/types.ts'
import type { CallChipIcon, CallChipStatus } from '../../ui/micro/CallChip.tsx'

/** The backend's pipeline (live/cycle.py), one chip each. */
export const STEPS: { phase: LivePhase; name: string; icon: CallChipIcon; expectedMs: number }[] = [
  { phase: 'discovery', name: 'find sources', icon: 'search', expectedMs: 60_000 },
  { phase: 'inspect', name: 'read pages', icon: 'file', expectedMs: 45_000 },
  { phase: 'extract', name: 'pull rows', icon: 'terminal', expectedMs: 60_000 },
  { phase: 'merge', name: 'merge', icon: 'edit', expectedMs: 5_000 },
]

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

/** Each chip's state from the current phase: earlier steps done, this one running, later ones waiting. */
export function stepStatus(s: Partial<LiveStatus>, i: number, hasData: boolean): CallChipStatus {
  const phase = s.phase ?? 'idle'
  if (phase === 'sleep') return 'done'
  if (phase === 'error') {
    // The backend doesn't say which step failed; the detail usually names it ("Discovery failed: …").
    const failed = /discover/i.test(s.detail ?? '') ? 0 : hasData ? 2 : 0
    return i < failed ? 'done' : i === failed ? 'error' : 'idle'
  }
  const at = STEPS.findIndex((x) => x.phase === phase)
  if (at < 0) return hasData ? 'done' : 'idle'
  return i < at ? 'done' : i === at ? 'running' : 'idle'
}
