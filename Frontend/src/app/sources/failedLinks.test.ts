import assert from 'node:assert/strict'
import { test } from 'node:test'
import { failedLinksCsv } from './failedLinks.ts'

const columns = ['url', 'domain', 'stage', 'outcome', 'http_status', 'reason', 'checked_at']
const column_labels = ['Link', 'Site', 'Step', 'Outcome', 'HTTP status', 'Reason', 'Checked at (UTC)']

test('failed links export with their labels, one line per link', () => {
  const csv = failedLinksCsv({
    columns,
    column_labels,
    rows: [{ url: 'https://a.test/x', domain: 'a.test', stage: 'research', outcome: 'blocked', http_status: 403, reason: 'The site refused, (HTTP 403)', checked_at: '2026-10-07 01:00:00' }],
  })
  const lines = csv.replace('\ufeff', '').split('\r\n')
  assert.equal(lines[0], 'Link,Site,Step,Outcome,HTTP status,Reason,Checked at (UTC)')
  assert.equal(lines[1], 'https://a.test/x,a.test,research,blocked,403,"The site refused, (HTTP 403)",2026-10-07 01:00:00')
  assert.ok(csv.startsWith('\ufeff'))
})

test('a scraped reason that looks like a formula is defused', () => {
  const csv = failedLinksCsv({
    columns,
    column_labels,
    rows: [{ url: 'https://a.test', domain: 'a.test', stage: 'scrape', outcome: 'error', http_status: '', reason: '=HYPERLINK("x")', checked_at: '' }],
  })
  assert.ok(csv.includes(`"'=HYPERLINK(""x"")"`))
})

test('no failures still gives a header line', () => {
  assert.equal(failedLinksCsv({ columns, column_labels, rows: [] }).split('\r\n').length, 1)
})
