import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router'
import { buttonClass } from '../ui/buttonClass.ts'
import { BanIcon } from '../ui/icons.tsx'
import { Mark } from '../ui/Mark.tsx'
import { useArrived } from '../ui/useArrived.ts'
import { safeNext, useAuth } from './auth/authContext.ts'
import { AuthFrame } from './AuthFrame.tsx'

/** Sign in with Google. Signed-in visitors go straight on to where they were headed. */
export default function LoginPage() {
  const { session, loading, signInWithGoogle } = useAuth()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const arrived = useArrived()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!loading && session) return <Navigate to={next} replace />

  const start = async () => {
    setBusy(true)
    setError(null)
    const failure = await signInWithGoogle(next)
    // On success the browser is already leaving for Google; only a failure comes back here.
    if (failure) {
      setError(failure)
      setBusy(false)
    }
  }

  return (
    <AuthFrame>
      <p className="font-mono text-micro text-ink-3">Sign in</p>
      <h1 className="mt-4 font-display font-wide text-section font-extrabold">
        Sign in to{' '}
        <Mark on={arrived} delay={300}>
          start a request.
        </Mark>
      </h1>
      <p className="mt-5 max-w-[46ch] text-lead text-ink-2">
        AWDAX uses your Google account to know it’s you. It asks only for your name, email address and profile
        picture.
      </p>

      <button
        type="button"
        onClick={start}
        disabled={busy || loading}
        aria-busy={busy || undefined}
        className={buttonClass('secondary', 'lg', 'mt-10')}
      >
        <img src="/google-g.svg" alt="" width={20} height={20} />
        {busy ? 'Opening Google…' : 'Continue with Google'}
      </button>

      {error && (
        <p role="alert" className="mt-5 flex items-start gap-2 text-small text-ink">
          <BanIcon className="mt-0.5 shrink-0 text-blocked" />
          {error}
        </p>
      )}

      <p className="mt-10 border-t-2 border-ink pt-4 text-small text-ink-3">
        Signing in never starts a run. Nothing runs until you approve a plan.
      </p>
    </AuthFrame>
  )
}
