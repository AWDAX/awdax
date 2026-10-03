import { useRef, useState } from 'react'
import { useInView, useMotionValueEvent, useScroll } from 'motion/react'
import { Container } from '../../ui/Container.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { useMediaQuery } from '../../ui/useMediaQuery.ts'
import { STEPS } from '../how/steps.tsx'
import type { Step } from '../how/steps.tsx'
import { Section, SectionHead } from '../SectionHead.tsx'

/**
 * Ask → Plan → Run → Review → Use. On wide screens the list pins while the section scrolls and a
 * yellow band sweeps onto the current step. Below lg it is a plain list; the row being read is highlighted.
 */
export function HowItWorks() {
  const wide = useMediaQuery('(min-width: 64rem)')
  const pinRef = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)
  const { scrollYProgress } = useScroll({ target: pinRef, offset: ['start start', 'end end'] })
  useMotionValueEvent(scrollYProgress, 'change', (p) => {
    // Below lg nothing is pinned and rows follow the reader instead; skip the re-renders.
    if (!wide) return
    setActive(Math.min(STEPS.length - 1, Math.max(0, Math.floor(p * STEPS.length))))
  })

  return (
    <Section id="how" labelledBy="how-title" fit={false}>
      <Container>

        <SectionHead
          id="how-title"
          index="01"
          kicker="How it works"
          title={(seen) => (
            <>
              Five steps. <Mark on={seen} delay={350}>You approve the second.</Mark>
            </>
          )}
          lede="AWDAX shows the plan first, runs only what you approve and hands back a dataset you can check, value by value."
        />
      </Container>

      {/* 60vh of scroll per step while pinned. */}
      <div ref={pinRef} className="mt-12 md:mt-16 lg:mt-4 lg:h-[400vh]">
        <div className="lg:sticky lg:top-16 lg:flex lg:h-[calc(100dvh-4rem)] lg:flex-col lg:justify-center lg:py-8">
          <Container className="lg:h-full">
            <ol className="flex flex-col border-b-2 border-ink lg:h-full">
              {STEPS.map((step, i) => (
                <StepRow key={step.key} step={step} index={i} active={active} wide={wide} />
              ))}
            </ol>
          </Container>
        </div>
      </div>
    </Section>
  )
}

function StepRow({ step, index, active, wide }: { step: Step; index: number; active: number; wide: boolean }) {
  const ref = useRef<HTMLLIElement>(null)
  // Not `once`: on phones the band follows the reader instead of painting the whole list yellow.
  const inView = useInView(ref, { amount: 0.6 })
  const on = wide ? index === active : inView
  const tone = on ? 'text-ink' : wide && index < active ? 'text-ink-2' : wide ? 'text-ink-3' : 'text-ink'

  return (
    <li
      ref={ref}
      aria-current={wide && on ? 'step' : undefined}
      className="relative border-t-2 border-ink lg:min-h-0 lg:flex-1"
    >
      {/* The highlighter band: sweeps in from the left onto the current step. */}
      <span
        aria-hidden
        className={`absolute inset-0 origin-left bg-signal transition-transform duration-900 ease-draw ${on ? 'scale-x-100' : 'scale-x-0'}`}
      />
      <div className="relative grid h-full items-center gap-x-6 gap-y-3 px-3 py-6 sm:px-4 lg:grid-cols-[3rem_minmax(0,0.9fr)_minmax(0,1.2fr)_minmax(0,1.5fr)] lg:py-2">
        <span className={`font-mono text-small ${on ? 'text-ink' : 'text-ink-3'}`}>{String(index + 1).padStart(2, '0')}</span>
        <h3 className={`font-display font-wide text-h2 font-extrabold ${tone}`}>{step.name}</h3>
        <p className={`max-w-[46ch] text-body ${on || !wide ? 'text-ink' : 'text-ink-3'}`}>
          {step.line}
        </p>
        <div
          aria-hidden={wide && !on}
          className={`rounded-control border-2 border-ink bg-surface p-3 ${wide && !on ? 'invisible' : ''}`}
        >
          {step.visual(on)}
        </div>
      </div>
    </li>
  )
}
