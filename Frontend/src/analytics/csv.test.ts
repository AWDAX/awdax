import assert from 'node:assert/strict'
import { test } from 'node:test'
import { parseDelimited } from './csv.ts'

test('quoted commas, escaped quotes and line breaks inside a field', () => {
  const t = parseDelimited('model,price,note\r\n"Nexon, EV","₹12,49,000","said ""fast""\nnew line"\r\nTiago,7.99 lakh,\r\n')
  assert.deepEqual(t.columns, ['model', 'price', 'note'])
  assert.deepEqual(t.rows[0], ['Nexon, EV', '₹12,49,000', 'said "fast"\nnew line'])
  assert.deepEqual(t.rows[1], ['Tiago', '7.99 lakh', ''])
  assert.equal(t.rows.length, 2)
})

test('byte-order mark, semicolons, blank and repeated headers', () => {
  const t = parseDelimited('\ufeffname;;name\na;1;b\n\n')
  assert.equal(t.delimiter, ';')
  assert.deepEqual(t.columns, ['name', 'Column 2', 'name (2)'])
  assert.deepEqual(t.rows, [['a', '1', 'b']])
})

test('tabs and short rows are padded', () => {
  const t = parseDelimited('a\tb\tc\n1\t2\n')
  assert.deepEqual(t.rows, [['1', '2', '']])
})
