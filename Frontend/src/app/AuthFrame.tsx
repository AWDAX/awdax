import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { Container } from '../ui/Container.tsx'

/** The frame for sign-in screens: the wordmark home link on a 2px rule, then one narrow column. */
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="border-b-2 border-ink">
        <Container className="flex h-16 items-center">
          <Link
            to="/"
            className="rounded-sm font-display font-wide text-h3 font-extrabold tracking-tight focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink"
          >
            AWDAX
          </Link>
        </Container>
      </header>
      <main id="main" className="flex flex-1 items-center py-16">
        <Container>
          <div className="max-w-[40rem]">{children}</div>
        </Container>
      </main>
    </div>
  )
}
