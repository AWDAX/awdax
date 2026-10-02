import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createFuseLatch } from './fuseLatch.ts'

test('arm then finish commits once, and a later unmount does not commit again', () => {
  const latch = createFuseLatch()
  latch.arm()
  assert.equal(latch.finish(), true)
  assert.equal(latch.unmount(), false)
})

test('arm then unmount commits once, and a later finish does not commit again', () => {
  const latch = createFuseLatch()
  latch.arm()
  assert.equal(latch.unmount(), true)
  assert.equal(latch.finish(), false)
})

test('arm, undo, then finish and unmount: nothing commits', () => {
  const latch = createFuseLatch()
  latch.arm()
  latch.undo()
  assert.equal(latch.finish(), false)
  assert.equal(latch.unmount(), false)
})

test('never armed: unmount commits nothing (an idle button mounted and unmounted, as StrictMode does)', () => {
  const latch = createFuseLatch()
  assert.equal(latch.unmount(), false)
})

test('arm, undo, arm again, then finish commits once', () => {
  const latch = createFuseLatch()
  latch.arm()
  latch.undo()
  latch.arm()
  assert.equal(latch.finish(), true)
  assert.equal(latch.finish(), false)
})

test('an idle unmount does not disable the latch: arm then finish still commits once', () => {
  const latch = createFuseLatch()
  assert.equal(latch.unmount(), false)
  latch.arm()
  assert.equal(latch.finish(), true)
})

test('after it commits, the latch can be armed and committed again (a Reset button is used more than once)', () => {
  const latch = createFuseLatch()
  latch.arm()
  assert.equal(latch.finish(), true)
  latch.arm()
  assert.equal(latch.finish(), true)
})

test('a commit that makes the control unmount does not commit twice', () => {
  const latch = createFuseLatch()
  latch.arm()
  // the caller runs the action after finish() returned true; that action may unmount the control
  assert.equal(latch.finish(), true)
  assert.equal(latch.unmount(), false)
})
