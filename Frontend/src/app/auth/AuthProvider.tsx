import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { AuthError, Session } from '@supabase/supabase-js'
import { setStreamToken, setTokenSource } from '../../api/client.ts'
import { AuthContext, safeNext } from './authContext.ts'
import type { Auth } from './authContext.ts'
import { supabase } from './supabase.ts'

/** Supabase answered and said no (a forged, expired or revoked token), as opposed to being unreachable. */
const rejected = (error: AuthError) =>
  error.name === 'AuthSessionMissingError' || error.status === 401 || error.status === 403

/**
 * Holds the Supabase session for the app routes and keeps it current (sign-in, refresh, sign-out).
 * A session read from the browser is not trusted until Supabase confirms it once, so a hand-made
 * token in localStorage cannot open the app. `loading` stays true until then.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  // The user id Supabase has confirmed. Token refreshes keep the same id, so they don't re-check.
  // Deliberately not reset on sign-out: a forged session only arrives with a page load, which resets it.
  const [confirmed, setConfirmed] = useState<string | null>(null)

  useEffect(() => {
    // INITIAL_SESSION arrives once the client has started, after any OAuth code in the URL is exchanged.
    // Only set state in here: calling other Supabase methods inside this callback can deadlock.
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next)
      setReady(true)
      setStreamToken(next?.access_token ?? null, next?.expires_at)
    })
    // getSession refreshes an expired token first, so a call after a long sleep doesn't bounce off the proxy.
    setTokenSource(async () => (await supabase.auth.getSession()).data.session?.access_token ?? null)
    return () => {
      data.subscription.unsubscribe()
      setTokenSource(async () => null)
    }
  }, [])

  const userId = session?.user.id ?? null

  useEffect(() => {
    if (!userId || confirmed === userId) return
    let active = true
    supabase.auth.getUser().then(({ data, error }) => {
      if (!active) return
      if (error ? rejected(error) : data.user?.id !== userId) {
        // Clears the stored session; SIGNED_OUT then empties `session` and RequireAuth sends them to /login.
        void supabase.auth.signOut({ scope: 'local' })
        return
      }
      // Confirmed, or Supabase unreachable: keep a session we already had rather than sign someone
      // out over a bad connection.
      setConfirmed(userId)
    }).catch(() => {
      // Network failure or a thrown error: same policy as the error branch above, keep the session.
      if (active) setConfirmed(userId)
    })
    return () => {
      active = false
    }
  }, [userId, confirmed])

  const loading = !ready || (userId !== null && confirmed !== userId)

  const value = useMemo<Auth>(
    () => ({
      session: loading ? null : session,
      user: loading ? null : (session?.user ?? null),
      loading,
      signInWithGoogle: async (next) => {
        const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(safeNext(next))}`
        const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo } })
        return error ? error.message : null
      },
      signOut: async () => {
        await supabase.auth.signOut()
        // `storage` only fires in other tabs; nudge this tab's landing nav to show "Sign in" again.
        window.dispatchEvent(new StorageEvent('storage'))
      },
    }),
    [session, loading],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
