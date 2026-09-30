import { Link, Navigate, useLocation } from 'react-router'
import { BanIcon } from '../ui/icons.tsx'
import { safeNext, useAuth } from './auth/authContext.ts'
import { AuthFrame } from './AuthFrame.tsx'

/**
 * Where Google sends the visitor back. The Supabase client exchanges the ?code= on load; once the
 * session is in, go on to ?next=. Errors arrive in the query or the hash, depending on where they failed.
 */
export default function AuthCallback() {
  const { session, loading } = useAuth()
  const { search, hash } = useLocation()
  const query = new URLSearchParams(search)
  const fragment = new URLSearchParams(hash.slice(1))
  const error =
    query.get('error_description') ?? fragment.get('error_description') ?? query.get('error') ?? fragment.get('error')
  const next = safeNext(query.get('next'))

  if (!error && session) return <Navigate to={next} replace />

  if (error || !loading) {
    return (
      <AuthFrame>
        <h1 className="font-display font-wide text-section font-extrabold">Sign-in didn’t finish.</h1>
        <p role="alert" className="mt-5 flex items-start gap-2 text-body text-ink">
          <BanIcon className="mt-1 shrink-0 text-blocked" />
          {error ?? 'Google sent you back without a session. Please try again.'}
        </p>
        <p className="mt-8">
          <Link
            to={`/login?next=${encodeURIComponent(next)}`}
            className="rounded-sm text-body font-semibold text-ink underline decoration-2 underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink"
          >
            Try again
          </Link>
        </p>
      </AuthFrame>
    )
  }

  return (
    <AuthFrame>
      <p role="status" className="text-lead text-ink-2">
        Signing you in…
      </p>
    </AuthFrame>
  )
}
