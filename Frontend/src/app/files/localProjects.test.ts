import assert from 'node:assert/strict'
import { test } from 'node:test'
import { renamed } from './localProjects.ts'
import type { LocalProject } from './localProjects.ts'

const base = { id: 'a', title: 'Old', fileName: 'f.csv', fileSize: 1, created_at: 'c', updated_at: 'u', table: { columns: [], rows: [] } } as unknown as LocalProject

test('renamed trims the title and keeps updated_at', () => {
  const out = renamed(base, '  New  ')
  assert.equal(out?.title, 'New')
  assert.equal(out?.updated_at, 'u')
})

test('renamed writes nothing for a missing record or blank title', () => {
  assert.equal(renamed(undefined, 'New'), null)
  assert.equal(renamed(base, '   '), null)
})
