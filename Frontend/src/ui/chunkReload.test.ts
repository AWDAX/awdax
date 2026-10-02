import assert from 'node:assert/strict'
import { test } from 'node:test'
import { installChunkReload, isChunkLoadError, RELOAD_KEY, reloadOnce, shouldAutoReload } from './chunkReload.ts'

function memoryStorage(initial: Record<string, string> = {}) {
  const data = { ...initial }
  return {
    getItem: (k: string) => (k in data ? data[k] : null),
    setItem: (k: string, v: string) => {
      data[k] = v
    },
  }
}

const blocked = {
  getItem: () => {
    throw new Error('SecurityError')
  },
  setItem: () => {
    throw new Error('SecurityError')
  },
}

test('matches the chunk errors browsers throw', () => {
  for (const m of [
    'Failed to fetch dynamically imported module: https://x.test/assets/AppRoot-abc.js',
    'Importing a module script failed.',
    'error loading dynamically imported module: https://x.test/a.js',
    'Loading chunk 12 failed.',
    'Loading CSS chunk 3 failed.',
  ]) {
    assert.equal(isChunkLoadError(new TypeError(m)), true, m)
  }
  const named = new Error('boom')
  named.name = 'ChunkLoadError'
  assert.equal(isChunkLoadError(named), true)
  assert.equal(isChunkLoadError('Loading chunk 4 failed'), true)
})

test('ignores unrelated errors and non-errors', () => {
  assert.equal(isChunkLoadError(new Error('Cannot read properties of undefined')), false)
  assert.equal(isChunkLoadError(new Error('VITE_SUPABASE_URL must be set')), false)
  assert.equal(isChunkLoadError(null), false)
  assert.equal(isChunkLoadError(undefined), false)
  assert.equal(isChunkLoadError(42), false)
  assert.equal(isChunkLoadError({}), false)
})

test('shouldAutoReload: never reloaded, inside the window, after it', () => {
  assert.equal(shouldAutoReload(1_000_000, null), true)
  assert.equal(shouldAutoReload(1_010_000, 1_000_000), false)
  assert.equal(shouldAutoReload(1_030_000, 1_000_000), false)
  assert.equal(shouldAutoReload(1_030_001, 1_000_000), true)
  assert.equal(shouldAutoReload(1_005_000, 1_000_000, 1_000), true)
})

test('reloadOnce reloads the first time and records it', () => {
  const storage = memoryStorage()
  let calls = 0
  assert.equal(reloadOnce(storage, 5_000, () => calls++), true)
  assert.equal(calls, 1)
  assert.equal(storage.getItem(RELOAD_KEY), '5000')
})

test('reloadOnce: a second call inside the window does not reload', () => {
  const storage = memoryStorage()
  let calls = 0
  reloadOnce(storage, 5_000, () => calls++)
  assert.equal(reloadOnce(storage, 20_000, () => calls++), false)
  assert.equal(calls, 1)
})

test('reloadOnce: after the window it reloads again', () => {
  const storage = memoryStorage()
  let calls = 0
  reloadOnce(storage, 5_000, () => calls++)
  assert.equal(reloadOnce(storage, 40_000, () => calls++), true)
  assert.equal(calls, 2)
})

test('reloadOnce: blocked storage never reloads', () => {
  let calls = 0
  assert.equal(reloadOnce(blocked, 5_000, () => calls++), false)
  assert.equal(calls, 0)
})

test('reloadOnce: a garbage stored value counts as never reloaded', () => {
  const storage = memoryStorage({ [RELOAD_KEY]: 'nope' })
  let calls = 0
  assert.equal(reloadOnce(storage, 5_000, () => calls++), true)
  assert.equal(calls, 1)
})

test('installChunkReload handles vite:preloadError once per window and cancels the throw', () => {
  const listeners: Record<string, (e: Event) => void> = {}
  const target = { addEventListener: (type: string, fn: (e: Event) => void) => void (listeners[type] = fn) }
  const storage = memoryStorage()
  let calls = 0
  let t = 1_000
  installChunkReload(target, () => storage, () => t, () => calls++)
  let prevented = 0
  const event = { preventDefault: () => prevented++ } as unknown as Event
  listeners['vite:preloadError'](event)
  t += 5_000
  listeners['vite:preloadError'](event)
  assert.equal(prevented, 2)
  assert.equal(calls, 1)
})

test('installChunkReload survives storage that throws on access', () => {
  const listeners: Record<string, (e: Event) => void> = {}
  const target = { addEventListener: (type: string, fn: (e: Event) => void) => void (listeners[type] = fn) }
  let calls = 0
  installChunkReload(target, () => { throw new Error('denied') }, () => 1, () => calls++)
  assert.doesNotThrow(() => listeners['vite:preloadError']({ preventDefault() {} } as unknown as Event))
  assert.equal(calls, 0)
})
