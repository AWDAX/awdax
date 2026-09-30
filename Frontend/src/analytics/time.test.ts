import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runQuery, siteOf } from './aggregate.ts'
import { toString } from './decimal.ts'
import { evCars, evSales } from './fixtures.ts'
import { bucketOf, ordinal, parsePeriod } from './period.ts'
import { profileTable } from './profile.ts'

test('buckets: a date rolls up to its month, quarter and year', () => {
  const d = parsePeriod('14/08/2024')!
  assert.equal(bucketOf(d, 'month').key, '2024-08')
  assert.equal(bucketOf(d, 'quarter').key, '2024-Q3')
  assert.equal(bucketOf(d, 'year').key, '2024')
  assert.equal(bucketOf(parsePeriod('Mar 2025')!, 'quarter').label, 'Q1 2025')
})

test('ordinals space periods by real time, so a missing month is a gap', () => {
  assert.equal(ordinal('2025-01')! - ordinal('2024-05')!, 8)
  assert.equal(ordinal('2024-03-01')! - ordinal('2024-02-28')!, 2) // 2024 is a leap year
  assert.equal(ordinal('2025-Q1')! - ordinal('2024-Q4')!, 1)
})

test('launch dates grouped by year count every car exactly once', () => {
  const p = profileTable(evCars)
  const r = runQuery(p, { groupBy: 5, agg: 'count', bucket: 'year', sort: 'time' })
  assert.deepEqual(r.rows.map((x) => [x.key, toString(x.value!)]), [
    // Tigor · Tiago, ZS · Nexon, Comet, XUV400, eC3 · Punch, Windsor · Creta
    ['2021', '1'], ['2022', '2'], ['2023', '4'], ['2024', '2'], ['2025', '1'],
  ])
  assert.equal(r.used, 10)
})

test('web addresses group by site', () => {
  assert.equal(siteOf('https://www.vahan.example/ev?page=2'), 'vahan.example')
  const p = profileTable(evSales)
  const r = runQuery(p, { groupBy: 3, agg: 'count', sort: 'value-desc' })
  assert.deepEqual(r.rows.map((x) => [x.label, toString(x.value!)]), [['vahan.example', '6'], ['autodata.example', '3']])
})
