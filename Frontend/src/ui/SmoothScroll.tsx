import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router'
import { ReactLenis, useLenis } from 'lenis/react'
import type { LenisOptions } from 'lenis'
import 'lenis/dist/lenis.css'

// A softer glide than Lenis's default (lerp 0.1). In-page links (#how, #sources, #faq) glide too
// and stop below the sticky nav: Lenis honours each section's scroll-margin-top (scroll-mt-16), so
// no extra offset here. Lenis turns smoothing off for prefers-reduced-motion by itself.
const OPTIONS: LenisOptions = {
  autoRaf: true,
  lerp: 0.075,
  wheelMultiplier: 0.9,
  anchors: { duration: 1.4 },
  stopInertiaOnNavigate: true,
}

/** Lenis smooth scrolling for the whole page, plus a jump to the top when the route changes. */
export function SmoothScroll({ children }: { children: ReactNode }) {
  return (
    <ReactLenis root options={OPTIONS}>
      <TopOnRouteChange />
      {children}
    </ReactLenis>
  )
}

// Compares the path only: a route change always starts at the top, and same-page #anchors are left to
// Lenis. A future link to another route with a hash would land at the top, not at the anchor.
function TopOnRouteChange() {
  const lenis = useLenis()
  const { pathname } = useLocation()
  const last = useRef(pathname)
  useEffect(() => {
    if (last.current === pathname) return
    last.current = pathname
    lenis?.scrollTo(0, { immediate: true })
  }, [pathname, lenis])
  return null
}
