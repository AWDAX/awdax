import assert from 'node:assert/strict'
import test from 'node:test'
import type { ResearchSource } from './types.ts'
import { mergeSources } from './liveState.ts'

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
