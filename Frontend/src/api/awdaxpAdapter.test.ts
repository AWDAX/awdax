import assert from 'node:assert/strict'
import test from 'node:test'
import { PHASE } from './awdaxpAdapter.ts'

test('scraping and live phases are not idle', () => {
  assert.equal(PHASE.scraping, 'extract')
  assert.equal(PHASE.live, 'sleep')
})

test('the scraper\'s own phases (scraper.py) read as pulling rows, not "Waiting to start"', () => {
  assert.equal(PHASE.live_scraping, 'extract')
  assert.equal(PHASE.starting, 'extract')
})
