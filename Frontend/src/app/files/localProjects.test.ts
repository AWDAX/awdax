import assert from 'node:assert/strict'
import { test } from 'node:test'
import { filesDbName, listLocal, onLocalChange, renamed, setFilesOwner } from './localProjects.ts'
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

// Stands in for localStorage: only the two methods filesDbName uses.
const memoryStore = () => {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => m.get(k) ?? null,
    setItem: (k: string, v: string) => {
      m.set(k, v)
    },
  }
}

test('the first account on a browser keeps the shared files database', () => {
  const s = memoryStore()
  assert.equal(filesDbName('a', s), 'awdax')
  assert.equal(s.getItem('awdax.files.owner'), 'a')
})

test('another account gets a database of its own', () => {
  const s = memoryStore()
  filesDbName('a', s)
  assert.equal(filesDbName('b', s), 'awdax.b')
})

test('the first account keeps it on later sign-ins', () => {
  const s = memoryStore()
  filesDbName('a', s)
  filesDbName('b', s)
  assert.equal(filesDbName('a', s), 'awdax')
})

test('blocked storage never hands out the shared database', () => {
  const blocked = {
    getItem: () => {
      throw new Error('blocked')
    },
    setItem: () => {
      throw new Error('blocked')
    },
  }
  assert.equal(filesDbName('a', blocked), 'awdax.a')
})

test('storage that can be read but not written never hands out the shared database', () => {
  const readOnly = {
    getItem: () => null,
    setItem: () => {
      throw new Error('quota')
    },
  }
  assert.equal(filesDbName('a', readOnly), 'awdax.a')
})

// Node has no IndexedDB, so a rejection with this message can only come from the guard in open().
test('uploaded files stay closed until an account is confirmed', async () => {
  await assert.rejects(listLocal(), { message: 'Sign in to use uploaded files' })
})

test('lists re-read when the account changes, and only then', () => {
  let reads = 0
  const off = onLocalChange(() => {
    reads += 1
  })
  try {
    setFilesOwner('a')
    setFilesOwner('a')
    assert.equal(reads, 1)
    setFilesOwner('b')
    assert.equal(reads, 2)
  } finally {
    setFilesOwner(null)
    off()
  }
})
