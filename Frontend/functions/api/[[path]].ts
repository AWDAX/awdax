import { proxyToBackend } from '../../src/server/proxy.ts'
import type { ProxyEnv } from '../../src/server/proxy.ts'

/** Every /api/* call on awdax.pages.dev: checked for sign-in, then forwarded to the backend (src/server/proxy.ts). */
export const onRequest = ({ request, env }: { request: Request; env: ProxyEnv }) => proxyToBackend(request, env)
