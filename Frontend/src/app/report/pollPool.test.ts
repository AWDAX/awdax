import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isFresh, runPool } from './pollPool.ts'

const tick = () => new Promise<void>((r) => setTimeout(r, 2))

test('concurrency never exceeds the limit and every item runs', async () => {
  let running = 0
  let peak = 0
  const seen: number[] = []
  await runPool(Array.from({ length: 20 }, (_, i) => i), 6, async (i) => {
    running++
    peak = Math.max(peak, running)
    await tick()
    seen.push(i)
    running--
  })
  assert.equal(peak, 6)
  assert.equal(seen.length, 20)
})

test('isAlive=false stops new work', async () => {
  let alive = true
  const started: number[] = []
  await runPool([1, 2, 3, 4, 5, 6, 7, 8], 2, async (i) => {
    started.push(i)
    if (i === 2) alive = false
    await tick()
  }, () => alive)
  assert.deepEqual(started, [1, 2])
})

test('a result started before a manual change is ignored', () => {
  assert.equal(isFresh(100, 200), false, 'request began before the pause')
  assert.equal(isFresh(100, 100), false, 'same instant is not after')
  assert.equal(isFresh(300, 200), true)
  assert.equal(isFresh(100, undefined), true)
})
