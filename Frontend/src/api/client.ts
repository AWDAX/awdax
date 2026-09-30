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

/** FastAPI errors are `{ "detail": "..." }`; fall back to the raw text. */
function detailOf(text: string, status: number): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // not JSON
  }
  return text || `HTTP ${status}`
}

type TokenSource = () => Promise<string | null>
let tokenSource: TokenSource = async () => null

/**
 * The signed-in app hands over its Supabase session, so every call carries the user's token. The production
 * proxy (functions/api) checks it; the dev proxy and the backend ignore it.
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

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenSource().catch(() => null)
  let res: Response
  try {
    // Headers merge after the spread, so a caller's headers never wipe Content-Type (the docs' snippet did).
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(init.headers ?? {}) },
    })
  } catch {
    throw new ApiError(0, 'Can’t reach the AWDAX server. Is the backend running?')
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  // The backend (FastAPI) always answers errors in JSON. A non-JSON 404/405/501 comes from a static host that has
  // no /api route (Cloudflare answers POSTs with 405), so it means "not connected", never "chat deleted".
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
