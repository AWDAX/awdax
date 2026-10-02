import assert from 'node:assert/strict'
import { test } from 'node:test'
import { SIDEBAR_DEFAULT, SIDEBAR_MAX, SIDEBAR_MIN, WIDTH_KEY, clampWidth, readWidth, writeWidth } from './sidebarWidth.ts'

function memory() {
  const map = new Map<string, string>()
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  }
}

const throwing = {
  getItem: (): string | null => {
    throw new Error('blocked')
  },
  setItem: (): void => {
    throw new Error('blocked')
  },
}

test('clamp keeps the width between the bounds and rounds it', () => {
  assert.equal(clampWidth(SIDEBAR_MIN - 50), SIDEBAR_MIN)
  assert.equal(clampWidth(SIDEBAR_MAX + 50), SIDEBAR_MAX)
  assert.equal(clampWidth(300.6), 301)
  assert.equal(clampWidth(Number.NaN), SIDEBAR_DEFAULT)
})

test('a saved width comes back, clamped', () => {
  const s = memory()
  writeWidth(s, 310)
  assert.equal(readWidth(s), 310)
  s.setItem(WIDTH_KEY, '9999')
  assert.equal(readWidth(s), SIDEBAR_MAX)
})

test('nothing saved or garbage gives the default', () => {
  const s = memory()
  assert.equal(readWidth(s), SIDEBAR_DEFAULT)
  s.setItem(WIDTH_KEY, 'wide')
  assert.equal(readWidth(s), SIDEBAR_DEFAULT)
})

test('blocked or missing storage gives the default and never throws', () => {
  assert.equal(readWidth(throwing), SIDEBAR_DEFAULT)
  assert.equal(readWidth(null), SIDEBAR_DEFAULT)
  assert.doesNotThrow(() => writeWidth(throwing, 300))
  assert.doesNotThrow(() => writeWidth(null, 300))
})
