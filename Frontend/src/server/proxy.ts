import { createVerifier } from './jwt.ts'
import type { Verify } from './jwt.ts'

/**
 * The /api proxy behind awdax.pages.dev (functions/api/[[path]].ts). The backend has no CORS and no auth,
 * and is read-only for us, so the site calls its own origin and this forwards signed-in calls to it.
 * Set these in Cloudflare Pages → Settings → Variables and Secrets (Production).
 */
export interface ProxyEnv {
  /** Public HTTPS address of the AWDAX backend, such as the Cloudflare Tunnel URL. */
  AWDAX_API_ORIGIN?: string
  /** The Supabase project URL; tokens are checked against its published keys. */
  SUPABASE_URL?: string
  /** Optional comma-separated emails allowed through. Unset: any signed-in Google account. */
  ALLOWED_EMAILS?: string
  /** Optional. When set, sent upstream as `x-proxy-secret` so the backend can refuse calls that skip this proxy. */
  PROXY_SHARED_SECRET?: string
}

/** EventSource can't send headers, so the live stream carries the token in this cookie (src/api/client.ts). */
export const STREAM_COOKIE = 'awdax_token'

const FORWARD = ['accept', 'accept-language', 'content-type', 'last-event-id', 'authorization']
const PASS_BACK = ['content-type', 'etag', 'last-modified']

const NOT_SET_UP =
  'The AWDAX server isn’t connected to this site yet, so web requests can’t run here. Uploaded files and the sample run still work.'
const OFFLINE = 'The AWDAX server isn’t answering right now. Try again in a minute.'
const SIGNED_OUT = 'Your sign-in has expired. Reload the page and sign in again.'
const NOT_LISTED = 'This Google account isn’t on the AWDAX team list. Ask the owner to add it.'

const reply = (status: number, detail: string) => Response.json({ detail }, { status, headers: { 'cache-control': 'no-store' } })

const trim = (url: string | undefined) => url?.trim().replace(/\/+$/, '') || null

function tokenOf(request: Request): string | null {
  const auth = request.headers.get('authorization')
  if (auth?.startsWith('Bearer ')) return auth.slice(7).trim() || null
  for (const part of (request.headers.get('cookie') ?? '').split(';')) {
    const [name, ...value] = part.trim().split('=')
    if (name === STREAM_COOKIE) return value.join('=') || null
  }
  return null
}

// One verifier per isolate, so the Supabase keys are fetched once rather than on every call.
const verifiers = new Map<string, Verify>()
const verifierFor = (supabaseUrl: string) => {
  let verify = verifiers.get(supabaseUrl)
  if (!verify) verifiers.set(supabaseUrl, (verify = createVerifier(supabaseUrl)))
  return verify
}

export async function proxyToBackend(request: Request, env: ProxyEnv, verify?: Verify): Promise<Response> {
  const origin = trim(env.AWDAX_API_ORIGIN)
  const supabaseUrl = trim(env.SUPABASE_URL)
  // Fail closed: without a way to check sign-in, nothing goes through.
  if (!origin || !supabaseUrl) return reply(503, NOT_SET_UP)

  const token = tokenOf(request)
  const claims = token ? await (verify ?? verifierFor(supabaseUrl))(token) : null
  if (!claims) return reply(401, SIGNED_OUT)
  const allowed = (env.ALLOWED_EMAILS ?? '').split(',').map((e) => e.trim().toLowerCase()).filter(Boolean)
  if (allowed.length > 0 && !allowed.includes(claims.email?.toLowerCase() ?? '')) return reply(403, NOT_LISTED)

  // Pass user info and required headers to backend
  const headers = new Headers()
  for (const name of FORWARD) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  if (claims.sub) {
    headers.set('x-user-id', claims.sub)
  }
  if (token) {
    headers.set('authorization', `Bearer ${token}`)
  }
  if (env.PROXY_SHARED_SECRET) headers.set('x-proxy-secret', env.PROXY_SHARED_SECRET)
  const url = new URL(request.url)
  let upstream: Response
  try {
    upstream = await fetch(`${origin}${url.pathname}${url.search}`, {
      method: request.method,
      headers,
      body: request.method === 'GET' || request.method === 'HEAD' ? undefined : await request.arrayBuffer(),
      redirect: 'manual',
    })
  } catch {
    return reply(503, OFFLINE)
  }

  const type = upstream.headers.get('content-type') ?? ''
  // The backend answers errors in JSON. Anything else is the tunnel's own error page: the backend or tunnel is down.
  if (!upstream.ok && !type.includes('json')) return reply(upstream.status >= 500 ? 503 : upstream.status, upstream.status >= 500 ? OFFLINE : `HTTP ${upstream.status}`)

  const out = new Headers({ 'cache-control': 'no-store' })
  for (const name of PASS_BACK) {
    const value = upstream.headers.get(name)
    if (value) out.set(name, value)
  }
  // The body streams through untouched, so the live stream (text/event-stream) keeps flowing.
  return new Response(upstream.body, { status: upstream.status, headers: out })
}
