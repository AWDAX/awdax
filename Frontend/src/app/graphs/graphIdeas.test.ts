import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runQuery } from '../../analytics/aggregate.ts'
import { toString } from '../../analytics/decimal.ts'
import { profileTable } from '../../analytics/profile.ts'
import { defaultAgg } from '../../analytics/suggest.ts'
import { graphIdeas, graphProfile } from './graphIdeas.ts'

test('mixed charging durations share a minute axis and a category chart', () => {
  const profile = profileTable({
    columns: ['brand', 'charging_time'],
    rows: [['BMW', '31 min'], ['BMW', '35 min'], ['Kia', '10 hour'], ['Kia', '6 hour 30 min']],
    row_count: 4,
  })
  const duration = profile.columns[1]
  assert.equal(duration.kind, 'number')
  assert.equal(duration.suffix, 'min')
  assert.equal(defaultAgg(duration), 'avg')
  assert.deepEqual(duration.numbers?.map((value) => value && toString(value)), ['31', '35', '600', '390'])
  const chart = graphIdeas(profile).find((idea) => idea.id === 'measure-1')!
  assert.equal(chart.type, 'bar')
  assert.equal(chart.query.agg, 'avg')
  assert.deepEqual(runQuery(profile, chart.query).rows.map((row) => toString(row.value!)), ['495', '33'])
  assert.equal(graphIdeas(profile).find((idea) => idea.id === 'count-0')?.type, 'donut')
})

test('a real time series defaults to a line; a lone number uses observation labels', () => {
  const series = profileTable({ columns: ['month', 'sales'], rows: [['Jan 2024', '2'], ['Feb 2024', '3'], ['Mar 2024', '4']], row_count: 3 })
  assert.equal(graphIdeas(series).find((idea) => idea.id === 'measure-1')?.type, 'line')

  const plain = graphProfile(profileTable({ columns: ['value'], rows: [['12'], ['18'], ['21']], row_count: 3 }))
  const chart = graphIdeas(plain).find((idea) => idea.id === 'measure-0')!
  assert.equal(plain.columns[1].name, 'Observation')
  assert.equal(chart.type, 'bar')
  assert.equal(runQuery(plain, chart.query).used, 3)
})

test('text-only groups still get a distribution chart', () => {
  const profile = profileTable({ columns: ['status'], rows: [['open'], ['closed'], ['open']], row_count: 3 })
  assert.equal(graphIdeas(profile)[0]?.type, 'donut')
})

test('a partly populated charging time field keeps its valid values', () => {
  const profile = profileTable({
    columns: ['brand', 'charging_time'],
    rows: [['BMW', '31 min'], ['BMW', 'not specified'], ['Kia', '6 hour 30 min'], ['Kia', 'ask dealer'], ['MG', 'pending']],
    row_count: 5,
  })
  assert.equal(profile.columns[1].kind, 'number')
  const chart = graphIdeas(profile).find((idea) => idea.id === 'measure-1')!
  const result = runQuery(profile, chart.query)
  assert.equal(result.used, 2)
  assert.equal(result.excluded.length, 3)
})
