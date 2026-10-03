import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { Button } from './Button.tsx'
import { buttonClass } from './buttonClass.ts'
import { isChunkLoadError, reloadOnce } from './chunkReload.ts'

type FallbackArgs = { error: unknown; reset: () => void }

type Props = {
  children: ReactNode
  fallback?: (args: FallbackArgs) => ReactNode
  /** When this changes the boundary clears its error, so moving to another route recovers a page crash. */
  resetKey?: unknown
  scope?: 'app' | 'page'
}

type State = { error: unknown; failed: boolean }

const OK: State = { error: null, failed: false }

function copyFor(error: unknown): { title: string; line: string } {
  const message = error instanceof Error ? error.message : String(error)
  if (isChunkLoadError(error)) {
    return { title: 'A newer version is available', line: 'AWDAX was updated while this page was open. Reload to get the latest version.' }
  }
  if (message.includes('VITE_SUPABASE')) {
    return { title: 'Something went wrong', line: 'This build is missing its sign-in configuration.' }
  }
  return { title: 'Something went wrong', line: 'This page hit an unexpected error. Reloading usually fixes it.' }
}

/**
 * Plain elements and an `<a>`, no router or context: the router or a provider may be what just broke.
 */
function DefaultFallback({ error, scope }: { error: unknown; scope: 'app' | 'page' }) {
  const { title, line } = copyFor(error)
  return (
    <div
      role="alert"
      className={`flex items-center bg-canvas px-4 text-ink sm:px-8 ${scope === 'app' ? 'min-h-dvh' : 'min-h-full py-16'}`}
    >
      <div className="mx-auto w-full max-w-[40rem] border-2 border-ink bg-surface p-6 sm:p-8">
        <p className="font-display font-wide text-micro font-extrabold tracking-widest text-ink-2 uppercase">AWDAX</p>
        <h1 className="mt-3 font-display font-wide text-h2 font-extrabold">{title}</h1>
        <p className="mt-3 text-body text-ink-2">{line}</p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button onClick={() => window.location.reload()}>Reload page</Button>
          <a href="/" className={buttonClass('secondary')}>
            Back to home
          </a>
        </div>
      </div>
    </div>
  )
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = OK

  static getDerivedStateFromError(error: unknown): State {
    return { error, failed: true }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error('[awdax]', error, info.componentStack ?? undefined)
    if (isChunkLoadError(error)) {
      try {
        reloadOnce(sessionStorage, Date.now(), () => window.location.reload())
      } catch {
        // sessionStorage blocked: the fallback's reload button is the way out
      }
    }
  }

  componentDidUpdate(prev: Props) {
    if (this.state.failed && !Object.is(prev.resetKey, this.props.resetKey)) this.reset()
  }

  reset = () => this.setState(OK)

  render() {
    if (!this.state.failed) return this.props.children
    const { fallback, scope = 'app' } = this.props
    if (fallback) return fallback({ error: this.state.error, reset: this.reset })
    return <DefaultFallback error={this.state.error} scope={scope} />
  }
}
