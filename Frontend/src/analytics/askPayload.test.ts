import assert from 'node:assert/strict'
import test from 'node:test'
import { runQuery } from './aggregate.ts'
import { askPayload, presentQuery, toEngineQuery } from './askPayload.ts'
import { toString } from './decimal.ts'
import { evCars, evSales } from './fixtures.ts'
import { profileTable } from './profile.ts'

const cars = profileTable(evCars)
const sales = profileTable(evSales)

test('the planner gets readable columns and exact numbers, keyed per column', () => {
  const { columns, rows } = askPayload(cars)
  const price = columns.find((c) => c.key === 'price_inr')!
  assert.equal(price.kind, 'money')
  assert.equal(price.unit, 'INR')
  assert.equal(rows.length, 10)
  assert.equal(rows[0].price_inr, 1249000)
  assert.equal(rows[7].price_inr, null) // "N/A" stays missing, never 0
  assert.equal(rows[0].brand, 'Tata')
})

test('"in" values as written become the engine keys, so the AI plan counts the same rows as the parser', () => {
  const brand = cars.columns.find((c) => c.name === 'brand')!.index
  const price = cars.columns.find((c) => c.name === 'price_inr')!.index
  const q = toEngineQuery(cars, { agg: 'count', measure: price, filters: [{ column: brand, op: 'in', values: ['Tata'] }] })!
  // "tata " (trailing space, lower case) is the same brand
  assert.equal(toString(runQuery(cars, q).overall!), '4')
})

test('a year on a date column filters by the year bucket', () => {
  const month = sales.columns.find((c) => c.kind === 'period')!.index
  const units = sales.columns.find((c) => c.name === 'EV Units Sold')!.index
  const q = toEngineQuery(sales, { agg: 'sum', measure: units, filters: [{ column: month, op: 'in', values: ['2025'] }] })!
  assert.equal(q.filters![0].bucket, 'year')
  assert.equal(toString(runQuery(sales, q).overall!), '562493')
})

test('a plan naming a column this table lacks is rejected, not run', () => {
  assert.equal(toEngineQuery(cars, { agg: 'max', measure: 42 }), null)
  assert.equal(toEngineQuery(cars, { agg: 'count', filters: [{ column: 42, op: 'in', values: ['x'] }] }), null)
  assert.equal(toEngineQuery(cars, { agg: 'nope' as 'max' }), null)
})

test('the answer is worded and drawn from the plan shape', () => {
  const brand = cars.columns.find((c) => c.name === 'brand')!.index
  assert.deepEqual(presentQuery(cars, { agg: 'max', groupBy: brand, sort: 'value-desc', limit: 1 }), { intent: 'top', chart: 'bar' })
  assert.deepEqual(presentQuery(cars, { agg: 'avg' }), { intent: 'average', chart: 'kpi' })
})
