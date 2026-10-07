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

// Stands in for localStorage: only the method filesDbName uses.
const memoryStore = (owner?: string) => ({ getItem: (k: string) => (k === 'awdax.files.owner' ? (owner ?? null) : null) })

test('the account recorded as owner keeps the shared files database', () => {
  assert.equal(filesDbName('a', memoryStore('a')), 'awdax')
})

test('an account is never assumed to own the shared database', () => {
  // No owner on record: the shared database may hold several accounts' files, so nobody inherits it.
  assert.equal(filesDbName('a', memoryStore()), 'awdax.a')
})

test('another account gets a database of its own', () => {
  assert.equal(filesDbName('b', memoryStore('a')), 'awdax.b')
})

test('the owner keeps it on later sign-ins, whoever signed in between', () => {
  const s = memoryStore('a')
  filesDbName('b', s)
  assert.equal(filesDbName('a', s), 'awdax')
})

test('blocked storage never hands out the shared database', () => {
  const blocked = {
    getItem: () => {
      throw new Error('blocked')
    },
  }
  assert.equal(filesDbName('a', blocked), 'awdax.a')
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
