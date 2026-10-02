import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filterRows, runQuery } from './aggregate.ts'
import { answer } from './answer.ts'
import { evCars } from './fixtures.ts'
import { profileTable } from './profile.ts'

const cars = profileTable(evCars)
const past = cars.columns.length + 3
const brand = cars.columns.findIndex((c) => c.name === 'brand')
const price = cars.columns.findIndex((c) => c.name === 'price_inr')

// What a saved answer meets after a re-run dropped columns: the same query against a narrower table.
const narrow = profileTable({ columns: ['brand'], rows: [['Tata'], ['MG']], row_count: 2 })

test('a measure index past the last column gives a stale, empty result instead of throwing', () => {
  for (const agg of ['sum', 'avg', 'min', 'max', 'median'] as const) {
    const r = runQuery(cars, { groupBy: brand, measure: past, agg })
    assert.equal(r.stale, true, agg)
    assert.deepEqual(r.rows, [])
    assert.equal(r.overall, null)
    assert.equal(r.used, 0)
  }
  assert.equal(runQuery(cars, { measure: past, agg: 'distinct' }).stale, true)
})

test('a dimension index past the last column is stale, not silently one overall row', () => {
  const r = runQuery(cars, { groupBy: past, measure: price, agg: 'sum' })
  assert.equal(r.stale, true)
  assert.deepEqual(r.rows, [])
})

test('negative, fractional and non-numeric column references are stale too', () => {
  for (const bad of [-1, 1.5, Number.NaN, '1' as unknown as number]) {
    assert.equal(runQuery(cars, { groupBy: bad, agg: 'count' }).stale, true, String(bad))
    assert.equal(runQuery(cars, { measure: bad, agg: 'sum' }).stale, true, String(bad))
  }
})

test('a sum with no measure at all is stale rather than a crash on the first row', () => {
  assert.equal(runQuery(cars, { groupBy: brand, agg: 'sum' }).stale, true)
})

test('an empty table gives a defined result; refs into it are stale', () => {
  const empty = profileTable({ columns: [], rows: [], row_count: 0 })
  assert.equal(runQuery(empty, { groupBy: 0, measure: 1, agg: 'sum' }).stale, true)
  assert.equal(runQuery(empty, { agg: 'count' }).stale, false)
  const noRows = profileTable({ columns: ['brand', 'price'], rows: [], row_count: 0 })
  const r = runQuery(noRows, { groupBy: 0, measure: 1, agg: 'sum' })
  assert.equal(r.stale, false)
  assert.deepEqual(r.rows, [])
})

test('columns removed from the table: the old query is stale and the answer says so', () => {
  const q = { groupBy: brand, measure: price, agg: 'sum' as const }
  const r = runQuery(narrow, q)
  assert.equal(r.stale, true)
  const a = answer(narrow, 'Total price by brand', 'total', q, 'bar')
  assert.match(a.sentence, /no longer in the data/)
})

test('a valid query is not stale', () => {
  const r = runQuery(cars, { groupBy: brand, measure: price, agg: 'sum' })
  assert.equal(r.stale, false)
  assert.ok(r.rows.length > 0)
})

test('a filter on a missing column leaves the rows unfiltered (the filter has nothing to test)', () => {
  const all = filterRows(cars, [])
  assert.deepEqual(filterRows(cars, [{ column: past, op: 'in', values: ['tata'] }]), all)
  assert.deepEqual(filterRows(cars, [{ column: -1, op: 'present', values: [] }]), all)
  assert.deepEqual(filterRows(cars, [{ column: 1.5, op: 'gte', values: ['1'] }]), all)
})

test('a measure that is not numeric does not throw on grouped, limited queries', () => {
  const r = runQuery(cars, { groupBy: brand, measure: 0, agg: 'sum', limit: 1, other: true })
  assert.equal(r.stale, false)
  assert.equal(r.used, 0)
})
