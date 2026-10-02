import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { SourceView } from './buildSources.ts'
import { topSources } from './topSources.ts'

const view = (site: string, state: SourceView['state'], rows = 0): SourceView => ({ site, url: `https://${site}`, title: site, state, rows, share: null })

test('the site being read comes first, then the most rows, rejected last', () => {
  const ranked = topSources([
    view('a.example', 'rejected'),
    view('b.example', 'used', 3),
    view('c.example', 'validated'),
    view('d.example', 'used', 40),
    view('e.example', 'reading'),
  ])
  assert.deepEqual(ranked.map((s) => s.site), ['e.example', 'd.example', 'b.example', 'c.example', 'a.example'])
})

test('ties keep their original order', () => {
  const ranked = topSources([view('x.example', 'validated'), view('y.example', 'validated'), view('z.example', 'validated')])
  assert.deepEqual(ranked.map((s) => s.site), ['x.example', 'y.example', 'z.example'])
})
