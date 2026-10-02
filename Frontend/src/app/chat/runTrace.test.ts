import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runTrace } from './runTrace.ts'

test('mid-run: earlier steps done, the current one names the site it is on', () => {
  const t = runTrace({ phase: 'inspect' }, true, false, '91mobiles.com')
  assert.equal(t.busy, true)
  assert.deepEqual(t.steps, ['Found sources', 'Reading pages · 91mobiles.com'])
})

test('pulling rows lists the three steps so far', () => {
  assert.deepEqual(runTrace({ phase: 'extract' }, true, true).steps, ['Found sources', 'Read the pages', 'Pulling rows'])
})

test('a new run waiting to start is busy with no steps yet', () => {
  assert.deepEqual(runTrace({ phase: 'idle' }, true, false), { busy: false, steps: [], waiting: true })
})

test('up to date with rows: settled, every step ticked', () => {
  const t = runTrace({ phase: 'sleep' }, true, true)
  assert.equal(t.busy, false)
  assert.deepEqual(t.steps, ['Found sources', 'Read the pages', 'Pulled rows', 'Merged rows'])
})

test('an error or a paused run with no rows shows no trace', () => {
  assert.deepEqual(runTrace({ phase: 'error' }, true, true).steps, [])
  assert.deepEqual(runTrace({ phase: 'extract' }, false, false), { busy: false, steps: [], waiting: false })
})
