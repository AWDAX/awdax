import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { adoptUnscopedKeys, onScopeChange, scopedKey, setScopeUser } from './userScope.ts'

afterEach(() => setScopeUser(null))

const memory = (seed: Record<string, string> = {}) => {
  const m = new Map(Object.entries(seed))
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    keys: () => [...m.keys()].sort(),
  }
}

test('two accounts never share a key, and signed-out has its own', () => {
  setScopeUser('alice')
  const a = scopedKey('awdax.answers.c1')
  setScopeUser('bob')
  const b = scopedKey('awdax.answers.c1')
  setScopeUser(null)
  const none = scopedKey('awdax.answers.c1')
  assert.equal(new Set([a, b, none]).size, 3)
  assert.equal(a, 'awdax.answers.c1:alice')
})

test('listeners hear an account change, once per change', () => {
  let heard = 0
  const off = onScopeChange(() => void (heard += 1))
  setScopeUser('alice')
  setScopeUser('alice')
  setScopeUser('bob')
  off()
  setScopeUser('carol')
  assert.equal(heard, 2)
})

test('only the chats the account owns are moved to its scope', () => {
  const store = memory({
    'awdax.answers.mine': 'A1',
    'awdax.visits.mine': 'V1',
    'awdax.answers.theirs': 'A2',
    'awdax.dashboard.v2.theirs': 'D2',
  })
  setScopeUser('alice')
  adoptUnscopedKeys(['awdax.answers.', 'awdax.visits.', 'awdax.dashboard.v2.'], ['mine'], store)
  assert.equal(store.getItem('awdax.answers.mine:alice'), 'A1')
  assert.equal(store.getItem('awdax.visits.mine:alice'), 'V1')
  assert.equal(store.getItem('awdax.answers.mine'), null)
  // someone else's chat: untouched, and not readable under alice's scope
  assert.equal(store.getItem('awdax.answers.theirs'), 'A2')
  assert.equal(store.getItem('awdax.answers.theirs:alice'), null)
  assert.deepEqual(store.keys(), ['awdax.answers.mine:alice', 'awdax.answers.theirs', 'awdax.dashboard.v2.theirs', 'awdax.visits.mine:alice'])
})

test('a value already saved under the scope is not overwritten', () => {
  const store = memory({ 'awdax.answers.c:alice': 'new', 'awdax.answers.c': 'old' })
  setScopeUser('alice')
  adoptUnscopedKeys(['awdax.answers.'], ['c'], store)
  assert.equal(store.getItem('awdax.answers.c:alice'), 'new')
  assert.equal(store.getItem('awdax.answers.c'), null)
})

test('blocked storage does not throw', () => {
  const blocked = {
    getItem: () => {
      throw new Error('blocked')
    },
    setItem: () => undefined,
    removeItem: () => undefined,
  }
  assert.doesNotThrow(() => adoptUnscopedKeys(['x.'], ['a'], blocked))
})
