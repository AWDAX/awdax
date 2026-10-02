import assert from 'node:assert/strict'
import test from 'node:test'
import type { DatasetTable, StreamedRows } from './types.ts'
import { createSnapshotGate } from './snapshotGate.ts'

const table = (ids: string[]): DatasetTable => ({
  columns: ['name'],
  rows: ids.map((id) => [id]),
  records: ids.map((id) => ({ id })) as DatasetTable['records'],
})

const frame = (ids: string[], total = ids.length): StreamedRows => ({
  run_id: 'r', lane: 'fast', source_url: 'https://example.org', columns: ['name'],
  rows: ids.map((id) => [id]),
  records: ids.map((id) => ({ id })) as StreamedRows['records'],
  partial_added: 0, accepted_total: total,
})

test('a frame that arrives during a snapshot is kept', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  assert.equal(gate.isLoading(), true)
  gate.buffer(frame(['b']))
  const out = gate.finish(gen, 'accepted', table(['a']))
  assert.deepEqual(out?.rows, [['a'], ['b']])
  assert.equal(gate.isLoading(), false)
})

test('a record id already in the snapshot appears once', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['a', 'b']))
  gate.buffer(frame(['b']))
  const out = gate.finish(gen, 'accepted', table(['a']))
  assert.deepEqual(out?.rows, [['a'], ['b']])
})

test('the buffer is cleared after a finished snapshot', () => {
  const gate = createSnapshotGate()
  gate.buffer(frame(['x']))
  const out = gate.finish(gate.begin('accepted'), 'accepted', table(['a']))
  assert.equal(out?.rows.length, 2)
  const again = gate.finish(gate.begin('accepted'), 'accepted', table(['a']))
  assert.deepEqual(again?.rows, [['a']])
})

test('a filter that changed mid-request makes the result stale', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  assert.equal(gate.finish(gen, 'partial', table(['a'])), null)
})

test('with two overlapping begins only the newest finishes', () => {
  const gate = createSnapshotGate()
  const first = gate.begin('accepted')
  const second = gate.begin('accepted')
  assert.equal(gate.finish(first, 'accepted', table(['a'])), null)
  assert.equal(gate.isLoading(), true)
  assert.deepEqual(gate.finish(second, 'accepted', table(['a']))?.rows, [['a']])
})

test('reset mid-load discards the result and empties the buffer', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['b']))
  gate.reset()
  assert.equal(gate.isLoading(), false)
  assert.equal(gate.finish(gen, 'accepted', table(['a'])), null)
  const next = gate.finish(gate.begin('accepted'), 'accepted', table(['a']))
  assert.deepEqual(next?.rows, [['a']])
})

test('a failed snapshot settles: no longer loading, buffer kept for the retry', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['b']))
  gate.settle(gen)
  assert.equal(gate.isLoading(), false)
  const retry = gate.finish(gate.begin('accepted'), 'accepted', table(['a']))
  assert.deepEqual(retry?.rows, [['a'], ['b']])
})

test('settle for an overtaken generation leaves the newer load running', () => {
  const gate = createSnapshotGate()
  const old = gate.begin('accepted')
  gate.begin('accepted')
  gate.settle(old)
  assert.equal(gate.isLoading(), true)
})

test('replaying an older frame never shrinks the row count', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['a'], 10))
  const out = gate.finish(gen, 'accepted', { ...table(['a', 'b']), row_count: 12 })
  assert.equal(out?.row_count, 12)
})

test('a filter change drops frames buffered for the old view', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['old']))
  assert.equal(gate.finish(gen, 'partial', table(['a'])), null)
  const next = gate.finish(gate.begin('partial'), 'partial', table(['a']))
  assert.deepEqual(next?.rows, [['a']])
})

test('dropBuffer forgets frames made stale by final scoring', () => {
  const gate = createSnapshotGate()
  const gen = gate.begin('accepted')
  gate.buffer(frame(['rejected-later']))
  gate.dropBuffer()
  assert.deepEqual(gate.finish(gen, 'accepted', table(['a']))?.rows, [['a']])
})
