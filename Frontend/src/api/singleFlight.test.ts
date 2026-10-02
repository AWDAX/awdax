import assert from 'node:assert/strict'
import test from 'node:test'
import { createSingleFlight, sortedIdKey } from './singleFlight.ts'

test('singleFlight ignores a second call while one is pending, then allows the next', async () => {
  const flight = createSingleFlight()
  let release: () => void = () => {}
  let calls = 0
  const first = flight.run(() => new Promise<void>((resolve) => { calls += 1; release = resolve }))
  assert.equal(flight.busy(), true)
  assert.equal(await flight.run(async () => { calls += 1 }), false)
  release()
  assert.equal(await first, true)
  assert.equal(flight.busy(), false)
  assert.equal(await flight.run(async () => { calls += 1 }), true)
  assert.equal(calls, 2)
})

test('singleFlight frees itself when the task throws', async () => {
  const flight = createSingleFlight()
  await assert.rejects(flight.run(async () => { throw new Error('boom') }), /boom/)
  assert.equal(flight.busy(), false)
})

test('sortedIdKey does not change when the list is reordered', () => {
  assert.equal(sortedIdKey([{ id: 'b' }, { id: 'a' }, { id: 'c' }]), 'a,b,c')
  assert.equal(sortedIdKey([{ id: 'c' }, { id: 'a' }, { id: 'b' }]), sortedIdKey([{ id: 'a' }, { id: 'b' }, { id: 'c' }]))
  assert.equal(sortedIdKey([]), '')
})
