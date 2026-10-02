import assert from 'node:assert/strict'
import test from 'node:test'
import type { ResearchSource } from './types.ts'
import { applyPatch, EMPTY_LIVE, mergeSources } from './liveState.ts'

test('applyPatch merges sources, merges status, defaults connected and replaces the rest', () => {
  const base = { ...EMPTY_LIVE, connected: false, rowsTotal: 3, sources: [source('validated')], status: { lane: 'fast' as const, current_source: 'a' } }
  const next = applyPatch(base, { sources: [source('inspecting')], status: { lane: 'deep' }, rowsTotal: 9 })
  assert.equal(next.sources[0].status, 'validated')
  assert.deepEqual(next.status, { lane: 'deep', current_source: 'a' })
  assert.equal(next.connected, true)
  assert.equal(next.rowsTotal, 9)
  assert.equal(applyPatch(base, { connected: false }).connected, false)
  const untouched = applyPatch(base, {})
  assert.equal(untouched.sources, base.sources)
  assert.equal(untouched.status, base.status)
})

const source = (status: string): ResearchSource => ({
  id: 'one', url: 'https://example.org/cars', title: 'Cars', status,
  accepted: 0, partial: 0, rejected: 0, reason: '', domain: 'example.org', origin: 'search',
  deep_accepted: 0, deep_notes: [],
})

test('an older source snapshot cannot erase a live discovery update', () => {
  assert.equal(mergeSources([source('validated')], [source('inspecting')])[0].status, 'validated')
  assert.equal(mergeSources([source('inspecting')], [source('validated')])[0].status, 'validated')
  assert.equal(mergeSources([source('validated')], [source('blocked')])[0].status, 'blocked')
})
