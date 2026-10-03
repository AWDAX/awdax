import assert from 'node:assert/strict'
import { test } from 'node:test'
import { hasSeenTutorial, markTutorialSeen, seenKey } from './tutorialSeen.ts'

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

test('unseen is false, then true after marking', () => {
  const s = memory()
  assert.equal(hasSeenTutorial(s, 'a'), false)
  markTutorialSeen(s, 'a')
  assert.equal(hasSeenTutorial(s, 'a'), true)
})

test('seen is per user', () => {
  const s = memory()
  markTutorialSeen(s, 'a')
  assert.equal(hasSeenTutorial(s, 'b'), false)
  assert.equal(hasSeenTutorial(s, null), false)
  assert.equal(seenKey(null), 'awdax.tutorial.seen.v1:anon')
})

test('throwing storage counts as seen and never throws on mark', () => {
  assert.equal(hasSeenTutorial(throwing, 'a'), true)
  assert.doesNotThrow(() => markTutorialSeen(throwing, 'a'))
})

test('null storage counts as seen and never throws on mark', () => {
  assert.equal(hasSeenTutorial(null, 'a'), true)
  assert.doesNotThrow(() => markTutorialSeen(null, 'a'))
})
