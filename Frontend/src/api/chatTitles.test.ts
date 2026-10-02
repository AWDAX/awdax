import assert from 'node:assert/strict'
import test from 'node:test'
import { migrateLocalTitlesToBackend, setChatTitle } from './chatTitles.ts'

const fail = (status: number) => Object.assign(new Error('x'), { status })

test('404 drops the pending title, other failures keep it', async () => {
  setChatTitle('gone', 'A')
  setChatTitle('down', 'B')
  const save = async (id: string) => {
    throw fail(id === 'gone' ? 404 : 502)
  }
  await migrateLocalTitlesToBackend(save)
  const retried: string[] = []
  await migrateLocalTitlesToBackend(async (id) => {
    retried.push(id)
  })
  assert.deepEqual(retried, ['down'])
})
