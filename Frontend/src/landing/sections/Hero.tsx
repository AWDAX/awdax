import { ButtonLink } from '../../ui/Button.tsx'
import { Container } from '../../ui/Container.tsx'
import { ArrowIcon } from '../../ui/icons.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { useArrived } from '../../ui/useArrived.ts'
import { HeroRun } from '../hero/HeroRun.tsx'



export function Hero() {
  const arrived = useArrived()
  return (
    <section aria-labelledby="hero-title" className="pt-12 pb-24 md:pt-16 md:pb-32 lg:pt-20">
      <Container>
        <h1 id="hero-title" className="font-display font-wide text-display font-extrabold">
          <span className="block">Describe the data.</span>
          <span className="block">
            Get a dataset{' '}
            <Mark on={arrived} delay={600}>
              you can check.
            </Mark>
          </span>
        </h1>
        <div className="mt-8 flex flex-col gap-6 md:mt-10 lg:flex-row lg:items-end lg:justify-between lg:gap-12">
          <p className="max-w-[44ch] text-lead text-ink-2">
            AWDAX plans the collection, reads only permitted sources, cleans the results and links every value back to
            the sentence it came from.
          </p>

          <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
            <ButtonLink to="/app" size="lg">
              Start a request <ArrowIcon />
            </ButtonLink>
            <a
              href="#how"
              className="group rounded-control text-body font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ink"
            >
              <Mark on={false} className="group-hover:mark-on group-focus-visible:mark-on">
                See how it works
              </Mark>
            </a>
          </div>


        </div>
      </Container>

      <Container className="mt-12 lg:mt-16">
        <HeroRun />
      </Container>
    </section>

  )
}
