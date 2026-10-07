import assert from 'node:assert/strict'
import { test } from 'node:test'
import { detailOf } from './errorText.ts'

test('524 gateway-timeout HTML page becomes a plain sentence', () => {
  const out = detailOf('<!DOCTYPE html><html><body>timeout</body></html>', 524)
  assert.equal(out, 'The AWDAX server didn’t answer (HTTP 524). Try again in a minute.')
})
test('502 plain text is kept', () => assert.equal(detailOf('Bad gateway', 502), 'Bad gateway'))
test('JSON detail wins', () => assert.equal(detailOf('{"detail":"Nope"}', 400), 'Nope'))
test('empty body falls back to the status', () => assert.equal(detailOf('', 500), 'HTTP 500'))
test('long plain text is cut to 200 chars', () => assert.equal(detailOf('x'.repeat(500), 500).length, 200))
