/**
 * Checks a Supabase access token with WebCrypto alone: ES256 over the project's published keys (JWKS).
 * Runs in the Cloudflare Pages Function (functions/api) and in Node for the tests.
 */

export type Claims = { sub: string; email?: string; exp: number }
export type Jwk = JsonWebKey & { kid?: string }
export type Verify = (token: string) => Promise<Claims | null>

const KEYS_TTL_MS = 10 * 60_000
/** A token naming an unknown key refetches the keys (rotation), but at most this often. */
const RETRY_MS = 30_000

function bytes(part: string): Uint8Array<ArrayBuffer> {
  const b64 = part.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (part.length % 4)) % 4)
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out
}

function json(part: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(new TextDecoder().decode(bytes(part)))
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : null
  } catch {
    return null
  }
}

export async function fetchJwks(supabaseUrl: string): Promise<Jwk[]> {
  const res = await fetch(`${supabaseUrl}/auth/v1/.well-known/jwks.json`, { signal: AbortSignal.timeout(5000) })
  if (!res.ok) throw new Error(`JWKS ${res.status}`)
  const body = (await res.json()) as { keys?: Jwk[] }
  return body.keys ?? []
}

/**
 * A verifier for one Supabase project. It accepts only a signed-in user's token: right key and signature,
 * this project as issuer, audience and role `authenticated`, not expired.
 */
export function createVerifier(
  supabaseUrl: string,
  loadKeys: () => Promise<Jwk[]> = () => fetchJwks(supabaseUrl),
  now: () => number = Date.now,
): Verify {
  const issuer = `${supabaseUrl}/auth/v1`
  let cache: { at: number; keys: Jwk[] } = { at: -Infinity, keys: [] }
  let inflight: Promise<void> | null = null

  const keyFor = async (kid: string): Promise<CryptoKey | null> => {
    const age = now() - cache.at
    if (age > KEYS_TTL_MS || (!cache.keys.some((k) => k.kid === kid) && age > RETRY_MS)) {
      // Concurrent callers share one fetch. A failed fetch keeps the old keys and waits RETRY_MS before trying again.
      inflight ??= loadKeys()
        .catch(() => cache.keys)
        .then((keys) => {
          cache = { at: now(), keys }
          inflight = null
        })
      await inflight
    }
    const jwk = cache.keys.find((k) => k.kid === kid)
    if (!jwk || jwk.kty !== 'EC' || jwk.crv !== 'P-256' || !jwk.x || !jwk.y) return null
    return crypto.subtle.importKey('jwk', { kty: 'EC', crv: 'P-256', x: jwk.x, y: jwk.y }, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify'])
  }

  return async (token) => {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const header = json(parts[0])
    const payload = json(parts[1])
    if (!header || !payload || header.alg !== 'ES256' || typeof header.kid !== 'string') return null
    try {
      const key = await keyFor(header.kid)
      if (!key) return null
      const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`)
      if (!(await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, key, bytes(parts[2]), signed))) return null
    } catch {
      return null
    }
    const aud = payload.aud
    const audience = aud === 'authenticated' || (Array.isArray(aud) && aud.includes('authenticated'))
    if (payload.iss !== issuer || !audience || payload.role !== 'authenticated') return null
    if (typeof payload.exp !== 'number' || payload.exp * 1000 <= now()) return null
    if (typeof payload.sub !== 'string' || !payload.sub) return null
    return { sub: payload.sub, email: typeof payload.email === 'string' ? payload.email : undefined, exp: payload.exp }
  }
}
