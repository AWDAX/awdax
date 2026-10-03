import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createListSequence } from './listSequence.ts'

test('a create during an in-flight read rejects the stale read', () => {
  const s = createListSequence()
  const t = s.begin()
  s.mutated()
  assert.equal(s.accept(t), false)
})
test('a rename during a read rejects it', () => {
  const s = createListSequence()
  const t = s.begin()
  s.mutated()
  assert.equal(s.accept(t), false)
})
test('a delete during a read rejects it', () => {
  const s = createListSequence()
  const t = s.begin()
  s.mutated()
  s.mutated()
  assert.equal(s.accept(t), false)
})
test('two reads resolving in reverse: the older is rejected', () => {
  const s = createListSequence()
  const older = s.begin()
  const newer = s.begin()
  assert.equal(s.accept(newer), true)
  assert.equal(s.accept(older), false)
})
test('slow reads overtaken by newer requests still land in order', () => {
  const s = createListSequence()
  const first = s.begin()
  const second = s.begin()
  const third = s.begin()
  assert.equal(s.accept(first), true)
  assert.equal(s.accept(second), true)
  assert.equal(s.accept(third), true)
})
test('a read started after a mutation is accepted', () => {
  const s = createListSequence()
  s.mutated()
  const t = s.begin()
  assert.equal(s.accept(t), true)
})
