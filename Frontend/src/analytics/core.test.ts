import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runQuery } from './aggregate.ts'
import { add, div, fromString, median, sum, toString } from './decimal.ts'
import type { Dec } from './decimal.ts'
import { evCars, evSales } from './fixtures.ts'
import { formatCompact, formatDec } from './format.ts'
import { parseNumber } from './parse.ts'
import { parsePeriod } from './period.ts'
import { profileTable } from './profile.ts'

const d = (s: string) => fromString(s)!
const num = (raw: string) => {
  const r = parseNumber(raw)
  assert.ok(r.ok, `expected ${raw} to parse`)
  return r.num
}

test('decimals are exact where floats drift', () => {
  assert.equal(toString(add(d('0.1'), d('0.2'))), '0.3')
  assert.equal(toString(sum(Array.from({ length: 10 }, () => d('0.1')))), '1')
  assert.equal(toString(div(d('1'), d('3'), 4)!), '0.3333')
  assert.equal(toString(div(d('2.5'), d('1'), 0)!), '2') // half to even
  assert.equal(toString(div(d('3.5'), d('1'), 0)!), '4')
  assert.equal(toString(median([d('1'), d('2'), d('4'), d('10')])!), '3')
})

test('numbers: Indian and Western grouping, currency, scale words, units', () => {
  assert.equal(toString(num('1,44,879').value), '144879')
  assert.equal(toString(num('1,234,567.50').value), '1234567.5')
  assert.equal(toString(num('₹12.49 Lakh').value), '1249000')
  const rs = num('Rs. 7.99 lakh')
  assert.equal(rs.currency, 'INR')
  assert.equal(toString(rs.value), '799000')
  assert.equal(toString(num('₹1.2 Cr').value), '12000000')
  assert.equal(toString(num('$2.5M').value), '2500000')
  assert.equal(toString(num('(1,200)').value), '-1200')
  assert.equal(toString(num('−3.5').value), '-3.5')
  assert.equal(num('18.4%').percent, true)
  assert.equal(num('465 km').suffix, 'km')
  assert.equal(toString(num('₹ 5,000/-').value), '5000')
})

test('numbers: missing is not zero, and junk is refused with a reason', () => {
  for (const m of ['N/A', '—', '', 'not found', 'null']) {
    const r = parseNumber(m)
    assert.ok(!r.ok && r.missing, m)
  }
  for (const bad of ['10-20', '12,5', 'call for price', '1,23,4']) {
    const r = parseNumber(bad)
    assert.ok(!r.ok && !r.missing, bad)
  }
})

test('numbers: a range of one quantity counts as its lowest value', () => {
  const rs = num('Rs. 24.99 - 34.49 Lakh')
  assert.equal(toString(rs.value), '2499000')
  assert.equal(toString(rs.range!.low), '2499000')
  assert.equal(toString(rs.range!.high), '3449000')
  assert.equal(rs.currency, 'INR')
  const cr = num('₹1.95 - ₹2.65 Cr*')
  assert.equal(toString(cr.value), '19500000')
  assert.equal(toString(cr.range!.high), '26500000')
  assert.equal(toString(num('₹11.45 – ₹26.95 Lakh*').value), '1145000') // en dash
  const to = num('10 to 15 Lakh')
  assert.equal(toString(to.value), '1000000')
  assert.equal(toString(to.range!.high), '1500000')
  const km = num('450 - 500 km')
  assert.equal(toString(km.value), '450')
  assert.equal(km.suffix, 'km')
  const pct = num('10-15%')
  assert.equal(toString(pct.value), '10')
  assert.equal(pct.percent, true)
  const mixed = num('₹95 Lakh - ₹1.2 Cr') // both ends carry a scale word: each is read as written
  assert.equal(toString(mixed.value), '9500000')
  assert.equal(toString(mixed.range!.high), '12000000')
  const about = num('~10-12 lakh')
  assert.equal(toString(about.value), '1000000')
  assert.equal(about.approx, true)
  assert.equal(num('₹12.49 Lakh').range, undefined)
})

test('numbers: look-alikes of ranges stay refused', () => {
  const lookAlikes = [
    // No currency, scale word, unit or percent: as often a year, a page or a phone number as a quantity.
    '10-20', '2019–2024', '2024-25', '98765-43210',
    '₹20 - 10 Lakh', '$10 - ₹20', '10 km - 20 kWh', '₹10 - 15%',
    'Up to 500 km', '500 and above', '₹10 - 15 Lakh and above', '₹5 - 10 and above', '0-100 km/h in 9.5 s', '-10 - 20',
    '₹10* - ₹12 Lakh', '₹7.99 Lakh#',
  ]
  for (const bad of lookAlikes) {
    const r = parseNumber(bad)
    assert.ok(!r.ok && !r.missing, bad)
  }
})

test('numbers: a trailing footnote star is ignored', () => {
  assert.equal(toString(num('₹7.99 Lakh*').value), '799000')
  assert.equal(toString(num('₹7.99 Lakh †').value), '799000')
  assert.equal(toString(num('12**').value), '12')
  const na = parseNumber('N/A*')
  assert.ok(!na.ok && na.missing)
  assert.equal(toString(num('₹ 5,000/-').value), '5000')
})

test('periods sort in time order', () => {
  assert.equal(parsePeriod('Jan 2024')?.key, '2024-01')
  assert.equal(parsePeriod('2024-03')?.key, '2024-03')
  assert.equal(parsePeriod('14/09/2023')?.key, '2023-09-14')
  assert.equal(parsePeriod('09/14/2023')?.key, '2023-09-14')
  assert.equal(parsePeriod('03/04/2023')?.ambiguous, true)
  assert.equal(parsePeriod('Q2 2025')?.key, '2025-Q2')
  assert.equal(parsePeriod('FY 2024-25')?.key, 'FY2024-25')
  assert.equal(parsePeriod('March')?.key, 'M03')
  assert.equal(parsePeriod('31/02/2024'), null)
})

test('profile reads the EV sales table and joins Month + Year', () => {
  const p = profileTable(evSales)
  const kinds = p.columns.map((c) => c.kind)
  assert.deepEqual(kinds, ['period', 'period', 'number', 'url', 'period'])
  const units = p.columns[2]
  assert.equal(units.missing, 1)
  assert.equal(p.columns[4].virtual, true)
  assert.equal(p.columns[4].periods?.[6]?.key, '2025-01')
})

test('sum by month is exact and skips the missing month', () => {
  const p = profileTable(evSales)
  const r = runQuery(p, { groupBy: 4, measure: 2, agg: 'sum' })
  assert.deepEqual(
    r.rows.map((x) => x.key),
    ['2024-01', '2024-02', '2024-03', '2024-04', '2024-05', '2025-01', '2025-02', '2025-03'],
  )
  assert.equal(toString(r.overall!), '1316388')
  assert.equal(r.used, 8)
  assert.equal(r.matched, 9)
})

test('profile reads the cars table: money in INR, km unit, case-folded brands', () => {
  const p = profileTable(evCars)
  const price = p.columns[2]
  assert.equal(price.kind, 'money')
  assert.equal(price.currency, 'INR')
  assert.equal(p.columns[3].suffix, 'km')
  assert.equal(p.columns[1].kind, 'category')
  const byBrand = runQuery(p, { groupBy: 1, measure: 2, agg: 'sum' })
  const tata = byBrand.rows.find((x) => x.key === 'tata')!
  assert.equal(tata.count, 4) // "tata " folds into "Tata"
  assert.equal(toString(tata.value!), '4296000')
  const avg = runQuery(p, { measure: 2, agg: 'avg' })
  assert.equal(avg.used, 9)
  // 1,14,02,000 over 9 priced cars (Windsor EV is N/A) = 12,66,888.888… → .89
  assert.equal(formatDec(avg.overall as Dec, { currency: 'INR' }), '₹12,66,888.89')
})

test('top N with Other keeps the grand total', () => {
  const p = profileTable(evCars)
  const r = runQuery(p, { groupBy: 1, measure: 2, agg: 'sum', limit: 2, other: true })
  assert.equal(r.rows.length, 3)
  const total = sum(r.rows.map((x) => x.value!))
  assert.equal(toString(total), toString(r.overall!))
})

test('a range in a money column is flagged, counted at its lowest value, and queries say how many', () => {
  const p = profileTable({
    columns: ['Variant', 'Price'],
    rows: [['Base', '₹7.99 Lakh*'], ['Mid', '₹11.45 – ₹26.95 Lakh*'], ['Top', '₹9 Lakh']],
    row_count: 3,
  })
  const price = p.columns[1]
  assert.equal(price.kind, 'money')
  assert.equal(price.currency, 'INR')
  assert.deepEqual(price.numbers?.map((v) => v && toString(v)), ['799000', '1145000', '900000'])
  assert.deepEqual(price.ranged, [false, true, false])
  assert.equal(price.excluded.length, 0)
  assert.equal(p.columns[0].ranged, undefined)
  assert.equal(profileTable(evCars).columns[2].ranged, undefined)

  const avg = runQuery(p, { measure: 1, agg: 'avg' })
  assert.equal(toString(avg.overall!), '948000')
  assert.equal(avg.used, 3)
  assert.equal(avg.ranged, 1)
  const total = runQuery(p, { measure: 1, agg: 'sum' })
  assert.equal(toString(total.overall!), '2844000')
  assert.equal(total.ranged, 1)
  assert.equal(runQuery(p, { groupBy: 0, measure: 1, agg: 'sum' }).ranged, 1)
  assert.equal(runQuery(p, { agg: 'count' }).ranged, 0) // counting rows reads no value
  const without = runQuery(p, { measure: 1, agg: 'sum', filters: [{ column: 0, op: 'in', values: ['base', 'top'] }] })
  assert.equal(without.used, 2)
  assert.equal(without.ranged, 0) // only rows that were used are counted
})

test('formatting: Indian grouping for rupees, Western for dollars, compact axes', () => {
  assert.equal(formatDec(d('12345678.5'), { currency: 'INR' }), '₹1,23,45,678.5')
  assert.equal(formatDec(d('12345678.5'), { currency: 'USD' }), '$12,345,678.5')
  assert.equal(formatDec(d('-5'), { percent: true }), '−5%')
  assert.equal(formatCompact(d('12000000'), { currency: 'INR' }), '₹1.2Cr')
  assert.equal(formatCompact(d('144879')), '1.45L')
  assert.equal(formatCompact(d('50000'), {}, d('200000')), '0.5L') // one unit per axis
})
