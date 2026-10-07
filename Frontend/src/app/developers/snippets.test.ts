import assert from 'node:assert/strict'
import { test } from 'node:test'
import { claudeCodeCommand, claudeDesktopConfig, curlSnippet, groupByTag, operationsOf, researchSnippet, scopeLabel } from './snippets.ts'

const spec = {
  tags: [{ name: 'System' }, { name: 'Chats' }],
  paths: {
    '/api/instances': { post: { summary: 'Create', tags: ['Chats'] }, get: { summary: 'List', tags: ['Chats'] } },
    '/health': { get: { summary: 'Liveness', tags: ['System'] } },
    '/api/x': { parameters: [], get: { summary: 'No tag' } },
  },
}

test('operations come grouped by tag in the document’s order, GET before POST on one path', () => {
  const ops = operationsOf(spec)
  assert.deepEqual(
    ops.map((o) => `${o.method} ${o.path}`),
    ['GET /health', 'GET /api/instances', 'POST /api/instances', 'GET /api/x'],
  )
  assert.deepEqual(groupByTag(ops).map(([tag, list]) => [tag, list.length]), [['System', 1], ['Chats', 2], ['Other', 1]])
})

test('an empty or odd document gives no operations', () => {
  assert.deepEqual(operationsOf({}), [])
  assert.deepEqual(operationsOf({ paths: { '/a': { parameters: {} as never } } }), [])
})

test('snippets carry the site address and the key, with no doubled slash', () => {
  const key = 'awx_abc'
  assert.match(curlSnippet('https://awdax.example.com/', key), /^curl https:\/\/awdax\.example\.com\/api\/instances/)
  assert.ok(curlSnippet('https://x.test', key).includes('Authorization: Bearer awx_abc'))
  const research = researchSnippet('https://x.test', key)
  assert.ok(research.includes('https://x.test/api/instances/$ID/messages'))
  assert.equal(research.split('Bearer awx_abc').length, 2, 'the key appears once, in a variable')
  assert.equal(
    claudeCodeCommand('https://x.test/', key),
    'claude mcp add --transport http awdax https://x.test/api/mcp --header "Authorization: Bearer awx_abc"',
  )
  const config = JSON.parse(claudeDesktopConfig('https://x.test', key))
  assert.deepEqual(config.mcpServers.awdax.args.slice(-3), ['https://x.test/api/mcp', '--header', 'Authorization: Bearer awx_abc'].slice(-3))
})

test('a placeholder stands in until a key exists', () => {
  assert.ok(curlSnippet('https://x.test').includes('awx_YOUR_KEY'))
})

test('scope labels', () => {
  assert.equal(scopeLabel(['read']), 'Read only')
  assert.equal(scopeLabel(['read', 'write']), 'Read and write')
})
