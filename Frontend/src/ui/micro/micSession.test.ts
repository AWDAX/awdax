import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createStartGuard } from './micSession.ts'

test('a start is current until something else happens', () => {
  const g = createStartGuard()
  const gen = g.next()
  assert.equal(g.isCurrent(gen), true)
})

test('stop (cancel) before the permission grant makes the start stale', () => {
  const g = createStartGuard()
  const gen = g.next()
  g.cancel()
  assert.equal(g.isCurrent(gen), false)
})

test('two starts resolving in reverse order: only the newest is current', () => {
  const g = createStartGuard()
  const first = g.next()
  const second = g.next()
  // the newer one resolves first, then the older one
  assert.equal(g.isCurrent(second), true)
  assert.equal(g.isCurrent(first), false)
})

test('cancel invalidates every outstanding start, and a later start is current again', () => {
  const g = createStartGuard()
  const a = g.next()
  const b = g.next()
  g.cancel()
  assert.equal(g.isCurrent(a), false)
  assert.equal(g.isCurrent(b), false)
  const c = g.next()
  assert.equal(g.isCurrent(c), true)
  assert.equal(g.isCurrent(b), false)
})
