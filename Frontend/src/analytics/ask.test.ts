import assert from 'node:assert/strict'
import { test } from 'node:test'
import { answer } from './answer.ts'
import { parseQuestion } from './ask.ts'
import { evCars, evSales } from './fixtures.ts'
import { profileTable } from './profile.ts'
import { suggestCharts, suggestFollowUps } from './suggest.ts'

const cars = profileTable(evCars)
const sales = profileTable(evSales)

function ask(p: ReturnType<typeof profileTable>, q: string) {
  const parsed = parseQuestion(p, q)
  assert.ok(parsed.ok, `could not read: ${q}`)
  return answer(p, q, parsed.intent, parsed.query, parsed.chart)
}

test('highest price by brand ranks brands by summed price', () => {
  const a = ask(cars, 'Which brand has the highest price?')
  assert.equal(a.intent, 'top')
  assert.equal(a.result.rows[0].label, 'Tata')
  assert.match(a.sentence, /^Tata has the highest total price \(INR\): ₹42,96,000/)
})

test('average price, with an above-filter in lakh', () => {
  const a = ask(cars, 'average price above 12 lakh')
  assert.equal(a.intent, 'average')
  // At least ₹12 lakh: 12.49, 18.98, 15.49, 17.99, 12.49 → 77,44,000 / 5
  assert.equal(a.result.used, 5)
  assert.match(a.sentence, /₹15,48,800/)
})

test('trend over the joined Month + Year timeline', () => {
  const a = ask(sales, 'How did EV units sold change over time?')
  assert.equal(a.intent, 'trend')
  assert.equal(a.chart, 'line')
  assert.equal(a.result.rows.length, 8)
  assert.match(a.sentence, /from 1,44,879 in Jan 2024 to 2,31,540 in Mar 2025, up 59\.82%/)
})

test('year filter: total units in 2024', () => {
  const a = ask(sales, 'total units sold in 2024')
  assert.equal(a.result.used, 5)
  assert.match(a.sentence, /7,53,895/)
})

test('compare two named values', () => {
  const a = ask(cars, 'compare Tata vs MG price')
  assert.equal(a.intent, 'compare')
  assert.equal(a.result.rows.length, 2)
})

test('unreadable questions say so instead of guessing', () => {
  const r = parseQuestion(cars, 'hello there')
  assert.equal(r.ok, false)
})

test('suggestions: a KPI, a trend and a ranking for the sales table', () => {
  const types = suggestCharts(sales).map((s) => s.type)
  assert.deepEqual(types.slice(0, 4), ['kpi', 'kpi', 'kpi', 'kpi'])
  assert.equal(types[4], 'line')
  assert.ok(suggestFollowUps(sales).some((f) => f.intent === 'trend'))
  assert.ok(suggestFollowUps(cars).some((f) => f.intent === 'top'))
})
