import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import { AuthFrame } from '../AuthFrame.tsx'
import { setFilesOwner } from '../files/localProjects.ts'
import { useAuth } from './authContext.ts'
import { setScopeUser } from './userScope.ts'

// The agent preview has no account, so uploaded files get one here. Vite drops this from production builds.
if (import.meta.env.DEV && import.meta.env.MODE === 'agent') {
  setFilesOwner('agent')
  setScopeUser('agent')
}

/** Shows its children to signed-in visitors; everyone else goes to /login and comes back here after. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { session, loading } = useAuth()
  const { pathname, search } = useLocation()

  // Agent preview: `npm run dev:agent` (vite --mode agent) opens the app without Google, so agents and
  // Playwright can check screens. import.meta.env.DEV is false in every production build, so Vite
  // removes this branch there; a plain `npm run dev` still requires sign-in.
  if (import.meta.env.DEV && import.meta.env.MODE === 'agent') return children

  if (loading) {
    return (
      <AuthFrame>
        <p role="status" className="text-lead text-ink-2">
          Checking your sign-in…
        </p>
      </AuthFrame>
    )
  }
  if (!session) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />
  return children
}
