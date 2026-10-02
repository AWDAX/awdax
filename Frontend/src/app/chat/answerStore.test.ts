import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { Query } from '../../analytics/aggregate.ts'
import { evCars } from '../../analytics/fixtures.ts'
import { profileTable } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import { isStaleAnswer, newAnswer, parseAnswers } from './answerStore.ts'
import type { SavedAnswer } from './answerStore.ts'

const cars = profileTable(evCars)
const brand = cars.columns.findIndex((c) => c.name === 'brand')
const price = cars.columns.findIndex((c) => c.name === 'price_inr')
const query: Query = { groupBy: brand, measure: price, agg: 'sum' }
const base = { question: 'Total price by brand', intent: 'total' as const, chart: 'bar' as const, query }
const roundTrip = (items: unknown[]) => parseAnswers(JSON.stringify(items))
const legacy = (q: Query): SavedAnswer => ({ id: 'q1', createdAt: 'now', ...base, query: q })

test('a new answer stores the column signature of the table it was asked against', () => {
  const a = newAnswer(base, columnSignature(cars))
  assert.equal(a.signature, columnSignature(cars))
  assert.ok(a.id && a.createdAt)
  assert.equal(roundTrip([a])[0].signature, columnSignature(cars))
})

test('the signature names the real columns, in order, and ignores the virtual ones', () => {
  assert.equal(columnSignature(cars), 'model|brand|price_inr|range_km|body_type|launch_date')
})

test('an answer is current while the table keeps its columns', () => {
  assert.equal(isStaleAnswer(newAnswer(base, columnSignature(cars)), cars), false)
})

test('a different column set flags the answer even when its indexes still exist', () => {
  const a = newAnswer(base, columnSignature(cars))
  const reordered = profileTable({ ...evCars, columns: [...evCars.columns].reverse(), rows: evCars.rows.map((r) => [...r].reverse()) })
  assert.ok(reordered.columns.length > price && reordered.columns.length > brand)
  assert.equal(isStaleAnswer(a, reordered), true)
})

test('an answer whose signature differs is flagged and still returned by the store', () => {
  const kept = roundTrip([{ ...newAnswer(base, columnSignature(cars)), signature: 'other|columns' }])
  assert.equal(kept.length, 1)
  assert.equal(isStaleAnswer(kept[0], cars), true)
})

test('a legacy answer without a signature is kept when every index is valid for the table', () => {
  const kept = roundTrip([legacy(query)])
  assert.equal(kept.length, 1)
  assert.equal(kept[0].signature, undefined)
  assert.equal(isStaleAnswer(kept[0], cars), false)
})

test('a legacy answer without a signature is flagged, not deleted, when an index is out of range', () => {
  const past = cars.columns.length
  for (const q of [{ ...query, measure: past }, { ...query, groupBy: past }, { ...query, filters: [{ column: past, op: 'in' as const, values: ['tata'] }] }]) {
    const kept = roundTrip([legacy(q)])
    assert.equal(kept.length, 1)
    assert.equal(isStaleAnswer(kept[0], cars), true)
  }
})

test('a legacy answer against a table that lost columns is flagged', () => {
  const narrow = profileTable({ columns: ['brand'], rows: [['Tata']], row_count: 1 })
  assert.equal(isStaleAnswer(legacy(query), narrow), true)
})

test('a malformed saved query is flagged instead of reaching the renderer', () => {
  const broken = { id: 'q2', question: 'x', intent: 'total', chart: 'bar', createdAt: 'now' }
  for (const bad of [{ ...broken }, { ...broken, query: null }, { ...broken, query: { agg: 'nope' } }, { ...broken, query: { agg: 'sum', filters: [{ column: 0 }] } }]) {
    const kept = roundTrip([bad])
    assert.equal(kept.length, 1)
    assert.equal(isStaleAnswer(kept[0], cars), true)
  }
})

test('storage that is not a list of answers reads as empty; entries that are not answers are skipped', () => {
  assert.deepEqual(parseAnswers(null), [])
  assert.deepEqual(parseAnswers('not json'), [])
  assert.deepEqual(parseAnswers('{"a":1}'), [])
  assert.deepEqual(roundTrip([null, 3, 'x', { id: 7 }, { id: 'a' }]), [])
  assert.equal(roundTrip([null, newAnswer(base, columnSignature(cars))]).length, 1)
})
