import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import type { AddressInfo } from 'node:net'
import { after, before, test } from 'node:test'
import { createVerifier } from './jwt.ts'
import type { Jwk } from './jwt.ts'
import { proxyToBackend, STREAM_COOKIE } from './proxy.ts'

const SUPABASE = 'https://example.supabase.co'
const b64 = (data: Uint8Array | string) => Buffer.from(data).toString('base64url')

const pair = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify'])
const other = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify'])
const jwk: Jwk = { ...(await crypto.subtle.exportKey('jwk', pair.publicKey)), kid: 'k1' }

async function sign(claims: Record<string, unknown>, key = pair.privateKey, header: Record<string, unknown> = { alg: 'ES256', kid: 'k1', typ: 'JWT' }) {
  const body = `${b64(JSON.stringify(header))}.${b64(JSON.stringify(claims))}`
  const sig = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, key, new TextEncoder().encode(body))
  return `${body}.${b64(new Uint8Array(sig))}`
}

const soon = () => Math.floor(Date.now() / 1000) + 600
const user = (extra: Record<string, unknown> = {}) => ({
  iss: `${SUPABASE}/auth/v1`, aud: 'authenticated', role: 'authenticated', sub: 'u1', email: 'Team@Example.com', exp: soon(), ...extra,
})

let keyLoads = 0
const verify = createVerifier(SUPABASE, async () => (keyLoads++, [jwk]))

test('accepts a signed-in user and rejects everything else', async () => {
  assert.equal((await verify(await sign(user())))?.email, 'Team@Example.com')
  assert.equal(await verify(await sign(user(), other.privateKey)), null, 'wrong key')
  assert.equal(await verify(await sign(user({ exp: 1000 }))), null, 'expired')
  assert.equal(await verify(await sign(user({ iss: 'https://evil.supabase.co/auth/v1' }))), null, 'other project')
  assert.equal(await verify(await sign(user({ role: 'anon', aud: 'anon' }))), null, 'anon key')
  assert.equal(await verify(await sign(user(), pair.privateKey, { alg: 'HS256', kid: 'k1' })), null, 'alg swap')
  const [h, , s] = (await sign(user())).split('.')
  assert.equal(await verify(`${h}.${b64(JSON.stringify(user({ sub: 'admin' })))}.${s}`), null, 'tampered payload')
  assert.equal(await verify('not-a-token'), null)
  assert.equal(keyLoads, 1, 'keys are cached')
})

// A stand-in backend that echoes what reached it, and streams on /stream.
let backend = ''
const server = createServer((req, res) => {
  if (req.url?.startsWith('/api/instances/x/live/stream')) {
    res.writeHead(200, { 'content-type': 'text/event-stream' })
    res.write('data: {"rows_total":3}\n\n')
    return
  }
  if (req.url === '/api/html') {
    res.writeHead(502, { 'content-type': 'text/html' }).end('<html>tunnel error</html>')
    return
  }
  let body = ''
  req.on('data', (c) => (body += c))
  req.on('end', () => {
    res.writeHead(200, { 'content-type': 'application/json', 'set-cookie': 'x=1' })
    res.end(JSON.stringify({ method: req.method, url: req.url, body, auth: req.headers.authorization ?? null, cookie: req.headers.cookie ?? null, secret: req.headers['x-proxy-secret'] ?? null }))
  })
})
before(() => new Promise<void>((done) => server.listen(0, '127.0.0.1', () => ((backend = `http://127.0.0.1:${(server.address() as AddressInfo).port}`), done()))))
after(() => server.close())

const env = () => ({ AWDAX_API_ORIGIN: `${backend}/`, SUPABASE_URL: SUPABASE })
const call = (path: string, init: RequestInit = {}, e: Record<string, string | undefined> = env()) =>
  proxyToBackend(new Request(`https://awdax.pages.dev${path}`, init), e, verify)

test('forwards a signed-in call with authorization header and no cookies', async () => {
  const token = await sign(user())
  const res = await call('/api/instances?x=1', { method: 'POST', body: '{"title":"t"}', headers: { authorization: `Bearer ${token}`, cookie: 'a=b', 'content-type': 'application/json' } })
  assert.equal(res.status, 200)
  assert.deepEqual(await res.json(), { method: 'POST', url: '/api/instances?x=1', body: '{"title":"t"}', auth: `Bearer ${token}`, cookie: null, secret: null })
  assert.equal(res.headers.get('set-cookie'), null)
  assert.equal(res.headers.get('cache-control'), 'no-store')
})

test('PROXY_SHARED_SECRET is sent upstream when set, absent when unset, and never taken from the client', async () => {
  const token = await sign(user())
  const headers = { authorization: `Bearer ${token}` }
  const withSecret = await call('/api/instances', { headers }, { ...env(), PROXY_SHARED_SECRET: 's3cret' })
  assert.equal((await withSecret.json()).secret, 's3cret')
  const empty = await call('/api/instances', { headers }, { ...env(), PROXY_SHARED_SECRET: '' })
  assert.equal((await empty.json()).secret, null)
  const unset = await call('/api/instances', { headers })
  assert.equal((await unset.json()).secret, null)
  const spoofed = await call('/api/instances', { headers: { ...headers, 'x-proxy-secret': 'forged' } })
  assert.equal((await spoofed.json()).secret, null, 'client value is not forwarded')
  const overridden = await call('/api/instances', { headers: { ...headers, 'x-proxy-secret': 'forged' } }, { ...env(), PROXY_SHARED_SECRET: 's3cret' })
  assert.equal((await overridden.json()).secret, 's3cret')
})

test('concurrent cold verifications share one JWKS load', async () => {
  let loads = 0
  const v = createVerifier(SUPABASE, async () => {
    loads++
    await new Promise((r) => setTimeout(r, 20))
    return [jwk]
  })
  const token = await sign(user())
  const results = await Promise.all(Array.from({ length: 10 }, () => v(token)))
  assert.ok(results.every((c) => c?.sub === 'u1'))
  assert.equal(loads, 1)
})

test('the live stream authenticates by cookie and streams', async () => {
  const res = await call('/api/instances/x/live/stream', { headers: { cookie: `theme=dark; ${STREAM_COOKIE}=${await sign(user())}` } })
  assert.equal(res.headers.get('content-type'), 'text/event-stream')
  const reader = res.body!.getReader()
  const first = new TextDecoder().decode((await reader.read()).value)
  assert.equal(first, 'data: {"rows_total":3}\n\n', 'first event arrives while the stream stays open')
  await reader.cancel()
})

test('refuses without sign-in, off the list, or unconfigured', async () => {
  const token = await sign(user())
  assert.equal((await call('/api/instances')).status, 401)
  assert.equal((await call('/api/instances', { headers: { authorization: 'Bearer junk' } })).status, 401)
  const listed = { ...env(), ALLOWED_EMAILS: 'someone@else.com, team@example.com' }
  assert.equal((await call('/api/instances', { headers: { authorization: `Bearer ${token}` } }, listed)).status, 200)
  const unlisted = { ...env(), ALLOWED_EMAILS: 'someone@else.com' }
  const refused = await call('/api/instances', { headers: { authorization: `Bearer ${token}` } }, unlisted)
  assert.equal(refused.status, 403)
  assert.match((await refused.json()).detail, /team list/)
  const unset = await call('/api/instances', { headers: { authorization: `Bearer ${token}` } }, { SUPABASE_URL: SUPABASE })
  assert.equal(unset.status, 503)
})

test('a down backend or tunnel becomes a plain JSON message', async () => {
  const token = await sign(user())
  const html = await call('/api/html', { headers: { authorization: `Bearer ${token}` } })
  assert.equal(html.status, 503)
  assert.match((await html.json()).detail, /isn’t answering/)
  const down = await call('/api/instances', { headers: { authorization: `Bearer ${token}` } }, { AWDAX_API_ORIGIN: 'http://127.0.0.1:1', SUPABASE_URL: SUPABASE })
  assert.equal(down.status, 503)
})
