import assert from 'node:assert/strict'
import test from 'node:test'
import { isRunActive, runActivityChanged, shouldPoll } from './pollGate.ts'

test('shouldPoll is true only for a visible tab with an active run', () => {
  for (const phase of ['discovery', 'inspect', 'extract', 'merge'] as const) {
    assert.equal(shouldPoll(true, phase), true)
  }
})

test('shouldPoll is false when the tab is hidden', () => {
  assert.equal(shouldPoll(false, 'extract'), false)
})

test('shouldPoll is false for idle, sleep, error, stopped and an unknown phase', () => {
  for (const phase of ['idle', 'sleep', 'error', 'stopped', undefined] as const) {
    assert.equal(shouldPoll(true, phase), false)
  }
})

test('isRunActive follows the phase only: a paused chat still finishing its pass is active', () => {
  assert.equal(isRunActive('merge'), true)
  assert.equal(isRunActive('sleep'), false)
})

test('runActivityChanged fires when a run starts and when it finishes', () => {
  assert.equal(runActivityChanged('sleep', 'discovery'), true)
  assert.equal(runActivityChanged('merge', 'sleep'), true)
  assert.equal(runActivityChanged('extract', 'merge'), false)
  assert.equal(runActivityChanged('idle', 'sleep'), false)
})
