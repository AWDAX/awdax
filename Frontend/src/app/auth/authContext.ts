import { createContext, useContext } from 'react'
import type { Session, User } from '@supabase/supabase-js'

export type Auth = {
  session: Session | null
  user: User | null
  /** True until the stored session, or an OAuth code in the URL, has been read. */
  loading: boolean
  /** Leaves for Google. Resolves with an error message only if the redirect could not start. */
  signInWithGoogle: (next?: string) => Promise<string | null>
  signOut: () => Promise<void>
}

export const AuthContext = createContext<Auth | null>(null)

export function useAuth(): Auth {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used inside <AuthProvider>')
  return auth
}

/** Where to go after signing in. Same-site paths only, so ?next= can never send someone to another site. */
export function safeNext(next: string | null | undefined, fallback = '/app'): string {
  return next && next.startsWith('/') && !next.startsWith('//') && !next.startsWith('/\\') ? next : fallback
}
