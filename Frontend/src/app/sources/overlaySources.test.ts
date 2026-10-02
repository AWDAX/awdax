import assert from 'node:assert/strict'
import { test } from 'node:test'
import { overlaySources } from './buildSources.ts'

const api = (status: string) => [
  { url: 'https://www.carwale.com/new/electric-cars/', title: 'CarWale', status, accepted: 0, reason: '', domain: 'carwale.com', origin: 'search', deep_accepted: 0, deep_notes: [] },
]

test('a source the backend is inspecting reads "reading" while the run works', () => {
  assert.equal(overlaySources([], api('inspecting'), true)[0].state, 'reading')
})

test('once the run has stopped, a source left mid-inspection is no longer "reading"', () => {
  assert.equal(overlaySources([], api('inspecting'), false)[0].state, 'visited')
  assert.equal(overlaySources([], api('selected'), false)[0].state, 'visited')
})

test('finished sources keep their state whether or not the run works', () => {
  assert.equal(overlaySources([], api('complete'), false)[0].state, 'used')
  assert.equal(overlaySources([], api('validated'), false)[0].state, 'validated')
})
