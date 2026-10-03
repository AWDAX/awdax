import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Recording } from './replay.ts'
import { READ_MS, REPLAY_MS, beats, replayAt } from './replay.ts'

const live = (phase: string, status: string, rows: number, detail = '') => ({
  enabled: true,
  rows_total: rows,
  latest_run: { id: 'r1', instance_id: 'i1', phase, status, detail, rows_total: rows },
})

const src = (url: string, status: string) => ({
  id: url, url, title: url, status, accepted: 0, partial: 0, rejected: 0, reason: '', domain: url, origin: 'search', deep_accepted: 0, deep_notes: [],
})

const rec: Recording = {
  slug: 'demo',
  prompt: 'Electric cars under 20 lakh',
  title: 'Electric cars under 20 lakh',
  recordedAt: '2026-10-03T00:00:00Z',
  durationMs: 300_000,
  steps: [
    { t: 500, kind: 'message', message: { id: 1, role: 'user', text: 'Electric cars under 20 lakh', created_at: '2026-10-03T00:00:00Z' } },
    { t: 4_000, kind: 'status', state: live('planning', 'running', 0, 'Understanding your request…') },
    { t: 30_000, kind: 'source', source: src('https://a.example/cars', 'inspecting') },
    { t: 31_000, kind: 'event', event: { id: 1, run_id: 'r1', phase: 'rendering', detail: 'Anchor inspect (1/2): A', created_at: '' } },
    { t: 32_000, kind: 'status', state: live('rendering', 'running', 0, 'Rendering https://a.example/cars') },
    { t: 200_000, kind: 'source', source: src('https://a.example/cars', 'complete') },
    { t: 290_000, kind: 'status', state: live('complete', 'succeeded', 2) },
    { t: 291_000, kind: 'message', message: { id: 2, role: 'bot', text: 'Done: 2 rows.', created_at: '2026-10-03T00:04:51Z' } },
    { t: 291_000, kind: 'done' },
  ],
  final: {
    dataset: { columns: ['model', 'price'], rows: [['A', 10], ['B', 12]], row_count: 2 },
    sources: [src('https://a.example/cars', 'complete')],
    stats: null,
  },
}

test('beats start at 0, end on the last step, and each stays up long enough to read', () => {
  const b = beats(rec)
  assert.deepEqual(b[0], { step: 0, at: 0 })
  assert.equal(b.at(-1)!.step, rec.steps.length - 1)
  for (let i = 1; i < b.length; i++) {
    assert.ok(b[i].step > b[i - 1].step, 'steps move forward')
    assert.ok(b[i].at - b[i - 1].at >= READ_MS, `beat ${i} held ${b[i].at - b[i - 1].at} ms`)
  }
  assert.ok(b.at(-1)!.at <= REPLAY_MS + READ_MS, `ends at ${b.at(-1)!.at}`)
})

test('a burst of steps shows as one beat, not a flicker', () => {
  const burst: Recording = {
    ...rec,
    durationMs: 10_000,
    steps: Array.from({ length: 50 }, (_, i) => ({ t: i * 200, kind: 'event' as const, event: { id: i + 1, run_id: 'r1', phase: 'rendering', detail: `line ${i}`, created_at: '' } })),
  }
  const b = beats(burst)
  assert.ok(b.length < 50, `${b.length} beats for 50 steps`)
  assert.equal(b.at(-1)!.step, 49)
})

test('the start shows only the user request, no rows, and a live run waiting to start', () => {
  const s = replayAt(rec, 0)
  assert.deepEqual(s.messages.map((m) => m.role), ['user'])
  assert.equal(s.live.dataset, null)
  assert.equal(s.live.liveEnabled, true)
})

test('mid-run state comes from the recorded frames, through the app adapter', () => {
  const s = replayAt(rec, 4)
  assert.equal(s.live.status.phase, 'inspect')
  assert.equal(s.live.status.current_source, 'https://a.example/cars')
  assert.deepEqual(s.live.events.map((e) => e.detail), ['Anchor inspect (1/2): A'])
  assert.equal(s.live.sources[0].status, 'inspecting')
  assert.deepEqual(s.visits.map((v) => v.source), ['https://a.example/cars'])
})

test('the end has the reply, the rows and the final sources', () => {
  const s = replayAt(rec, rec.steps.length - 1)
  assert.equal(s.live.status.phase, 'sleep')
  assert.deepEqual(s.messages.map((m) => m.role), ['user', 'bot'])
  assert.equal(s.live.dataset?.rows.length, 2)
  assert.equal(s.live.rowsTotal, 2)
  assert.equal(s.live.sources[0].status, 'complete')
})

test('an index past the end clamps to the last step', () => {
  assert.equal(replayAt(rec, 99).live.dataset?.rows.length, 2)
})
