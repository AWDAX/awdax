import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router'
import { useLenis } from 'lenis/react'
import { Container } from '../ui/Container.tsx'
import { ButtonLink } from '../ui/Button.tsx'
import { Mark } from '../ui/Mark.tsx'
import { useSignedInHint } from './useSignedInHint.ts'


const links = [
  { href: '#how', label: 'How it works' },
  { href: '#sources', label: 'Sources' },
  { href: '#faq', label: 'FAQ' },
]

const focusRing = 'rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink'

export function Nav() {
  const [scrolled, setScrolled] = useState(false)
  // One button: "Sign in" for visitors, "Open the app" once signed in (/login sends a signed-in
  // visitor straight on to /app anyway, so a stale hint still lands in the right place).
  const signedIn = useSignedInHint()
  const { pathname } = useLocation()
  const lenis = useLenis()
  // Already on the landing page, the logo takes you back to the top (the route itself doesn't change).
  const toTop = () => {
    if (pathname !== '/') return
    if (lenis) lenis.scrollTo(0)
    else window.scrollTo({ top: 0 })
  }

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  return (
    <header
      className={`sticky top-0 z-50 border-b-2 transition-colors duration-300 ease-soft ${
        scrolled ? 'border-ink bg-canvas/90 backdrop-blur-md' : 'border-transparent bg-canvas'
      }`}
    >
      <Container className="flex h-16 items-center justify-between">
        <Link to="/" onClick={toTop} aria-label="AWDAX home" className={`flex items-center gap-2 ${focusRing}`}>
          {/* logo.jpg has a grey ground; the filters push it to white and multiply removes it.
              Replace with an SVG mark before launch. */}
          <span className="size-8 overflow-hidden">
            <img
              src="/logo.jpg"
              alt=""
              width={32}
              height={32}
              className="size-full scale-160 brightness-110 contrast-125 mix-blend-multiply"
            />
          </span>
          <span className="font-display font-wide text-h3 font-extrabold tracking-tight">AWDAX</span>
        </Link>
        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <a key={l.href} href={l.href} className={`group text-small font-medium text-ink ${focusRing}`}>
              <Mark on={false} className="group-hover:mark-on group-focus-visible:mark-on">
                {l.label}
              </Mark>
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          {signedIn ? <ButtonLink to="/app">Open the app</ButtonLink> : <ButtonLink to="/login">Sign in</ButtonLink>}
        </div>
      </Container>
    </header>
  )
}

