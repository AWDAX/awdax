import assert from 'node:assert/strict'
import test from 'node:test'
import { PHASE } from './awdaxpAdapter.ts'

test('scraping and live phases are not idle', () => {
  assert.equal(PHASE.scraping, 'extract')
  assert.equal(PHASE.live, 'sleep')
})
