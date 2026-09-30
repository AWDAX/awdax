import { Footer } from './Footer.tsx'
import { Nav } from './Nav.tsx'
import { ApprovePlan } from './sections/ApprovePlan.tsx'
import { CleanByDefault } from './sections/CleanByDefault.tsx'
import { Dashboards } from './sections/Dashboards.tsx'
import { Faq } from './sections/Faq.tsx'
import { FinalCta } from './sections/FinalCta.tsx'
import { Hero } from './sections/Hero.tsx'
import { HowItWorks } from './sections/HowItWorks.tsx'
import { PermittedSources } from './sections/PermittedSources.tsx'
import { Receipts } from './sections/Receipts.tsx'

export default function LandingPage() {
  return (
    <>
      <a
        href="#main"
        // Move keyboard focus into the content too, so the next Tab starts there.
        onClick={() => document.getElementById('main')?.focus({ preventScroll: true })}
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-60 focus:rounded-control focus:bg-ink focus:px-4 focus:py-2 focus:text-on-ink"
      >
        Skip to content
      </a>
      <Nav />
      <main id="main" tabIndex={-1} className="outline-none">
        <Hero />
        <HowItWorks />
        <ApprovePlan />
        <Receipts />
        <CleanByDefault />
        <Dashboards />
        <PermittedSources />
        <Faq />
        <FinalCta />
      </main>
      <Footer />
    </>
  )
}
