import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runQuery } from './aggregate.ts'
import { toString } from './decimal.ts'
import { profileTable } from './profile.ts'
import { parseRunReport, withoutMasterTable } from './runReport.ts'
import { sampleReport, sampleTable } from './sampleRun.ts'
import { measures } from './suggest.ts'

test('the run report reads back into validated and rejected sources', () => {
  const r = parseRunReport(sampleReport)!
  assert.equal(r.status, 'success')
  assert.equal(r.sources.length, 2)
  assert.deepEqual(
    r.sources.map((s) => [s.rank, s.url, s.access, s.quality, s.authority, s.relevance, s.format]),
    [
      [1, 'https://vahan.example/ev/monthly', 'js_rendered', 9, 10, 9, 'dashboard'],
      [2, 'https://autodata.example/india/ev-sales', 'http_static', 8, 7, 9, 'html_table'],
    ],
  )
  assert.equal(r.sources[0].confidence, 9)
  assert.deepEqual(r.sources[1].blockers, ['June 2024 row is blank on the page'])
  assert.equal(r.rejected.length, 4)
  assert.deepEqual(r.rejected[3], { title: 'Paywalled market report', url: 'https://market.example/ev-india', reason: 'Requires login.' })
  assert.deepEqual(r.fills.map((f) => [f.url, f.fillRate]), [['https://vahan.example/ev/monthly', 97], ['https://autodata.example/india/ev-sales', 94]])
  assert.equal(r.strategies.length, 3)
  assert.equal(r.actualRows, 54)
})

test('text without a report is not mistaken for one', () => {
  assert.equal(parseRunReport('**Live** — 24 rows in dataset.'), null)
})

test('the master table is cut from the thread, with its row count', () => {
  const { text, removedRows } = withoutMasterTable(sampleReport)
  assert.equal(removedRows, 54)
  assert.ok(!text.includes('| month |'))
  assert.ok(text.includes('Fill validation'))
})

test('sample rows split by website exactly', () => {
  const p = profileTable(sampleTable)
  const src = p.columns.findIndex((c) => c.name === 'source_url')
  const r = runQuery(p, { groupBy: src, agg: 'count', sort: 'value-desc' })
  assert.deepEqual(r.rows.map((x) => [x.label, toString(x.value!)]), [['vahan.example', '36'], ['autodata.example', '18']])
  const units = runQuery(p, { measure: 2, agg: 'sum' })
  assert.equal(units.used, 52) // two months are N/A at the source
})

test('segment codes like 2W and 4W are categories, and units sold is the measure', () => {
  const p = profileTable(sampleTable)
  assert.equal(p.columns[1].kind, 'category')
  assert.equal(measures(p)[0].name, 'units_sold')
})
