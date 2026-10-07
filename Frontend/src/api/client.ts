import { detailOf } from './errorText.ts'

/**
 * Fetch wrapper for the AWDAX backend. In dev, calls are same-origin and Vite proxies them
 * (vite.config.ts). VITE_API_BASE_URL points at a backend on another origin, which then needs CORS.
 */
export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type TokenSource = () => Promise<string | null>
let tokenSource: TokenSource = async () => null

/**
 * The signed-in app hands over its Supabase session, so every call carries the user's token. The backend
 * verifies who the caller is: it answers 401 to anything it cannot prove.
 */
export function setTokenSource(source: TokenSource) {
  tokenSource = source
}

/** EventSource can't send headers, so the live stream carries the token in a cookie scoped to /api. */
export function setStreamToken(token: string | null, expiresAt?: number) {
  const maxAge = !token ? 0 : expiresAt ? Math.max(0, Math.floor(expiresAt - Date.now() / 1000)) : 3600
  const secure = window.location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `awdax_token=${token ?? ''}; Path=/api; Max-Age=${maxAge}; SameSite=Strict${secure}`
}

/** Expiry (seconds since epoch) read from a token's payload; the token was already verified by its issuer. */
function expiryOf(token: string): number | undefined {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const exp = (JSON.parse(atob(part)) as { exp?: unknown }).exp
    return typeof exp === 'number' ? exp : undefined
  } catch {
    return undefined
  }
}

/**
 * Re-writes the stream cookie from the current session. The live stream and socket can't send headers, so each
 * (re)connect calls this first: a cookie that expired while the tab slept would otherwise sign the stream out.
 */
export function refreshStreamToken(): void {
  void tokenSource()
    .then((token) => {
      if (token) setStreamToken(token, expiryOf(token))
    })
    .catch(() => undefined)
}

export const SIGNED_OUT = 'Your sign-in has expired. Reload the page and sign in again.'
// Needs no identity. Everything else is somebody's data and goes out only with that person's token.
const OPEN_PATHS = new Set(['/health', '/ready'])
// `npm run dev:agent` opens the app without Google; Vite drops this branch from every production build.
const AGENT_PREVIEW = import.meta.env.DEV && import.meta.env.MODE === 'agent'

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenSource().catch(() => null)
  // No token, no request: sent bare, the backend could only refuse it (or, in dev mode, file it under a shared user).
  if (!token && !AGENT_PREVIEW && !OPEN_PATHS.has(path)) throw new ApiError(401, SIGNED_OUT)
  let res: Response
  try {
    // The caller's headers merge before Authorization, so they can neither wipe Content-Type (the docs' snippet did)
    // nor swap in someone else's identity.
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    })
  } catch {
    throw new ApiError(0, 'Can’t reach the AWDAX server. Is the backend running?')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  // The backend (FastAPI) always answers errors in JSON. A non-JSON 404/405/501 comes from a static host that has
  // no /api route (a static host answers POSTs with 405), so it means "not connected", never "chat deleted".
  const json = (res.headers.get('content-type') ?? '').includes('json')
  if (!res.ok && !json && [404, 405, 501].includes(res.status)) throw new ApiError(502, NOT_CONNECTED)
  if (!res.ok) throw new ApiError(res.status, detailOf(text, res.status))
  // A static host with no /api route answers with the site's own index.html (status 200). Say so plainly
  // instead of surfacing a JSON parse error.
  if (text.trimStart().startsWith('<')) throw new ApiError(502, NOT_CONNECTED)
  try {
    return (text ? JSON.parse(text) : undefined) as T
  } catch {
    throw new ApiError(502, NOT_CONNECTED)
  }
}

export const NOT_CONNECTED =
  'The AWDAX server isn’t connected to this site yet, so web requests can’t run here. Uploaded files and the sample run still work.'
