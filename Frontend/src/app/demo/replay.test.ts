import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Recording } from './replay.ts'
import { REPLAY_MS, replayAt, schedule } from './replay.ts'

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

test('schedule keeps order, starts at 0 and fits about REPLAY_MS', () => {
  const at = schedule(rec)
  assert.equal(at.length, rec.steps.length)
  assert.equal(at[0], 0)
  for (let i = 1; i < at.length; i++) assert.ok(at[i] >= at[i - 1])
  assert.ok(at.at(-1)! <= REPLAY_MS + 1_000, `ends at ${at.at(-1)}`)
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
