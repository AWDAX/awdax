import { useRef } from 'react'
import { samples } from '../../domain/fixtures/index.ts'
import { METHOD, PERMISSION } from '../../product/meta.ts'
import { Container } from '../../ui/Container.tsx'
import { BanIcon } from '../../ui/icons.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Strike } from '../../ui/Strike.tsx'
import { useSeen } from '../../ui/useSeen.ts'
import { Section, SectionHead } from '../SectionHead.tsx'

// docs/PRODUCT.md, "What AWDAX does not do".
const RULED_OUT = ['Get past a sign-in', 'Solve a CAPTCHA or work around a block', 'Read a path robots.txt disallows', 'Fill a missing value with a guess']

// The robots.txt example is the Sales leads sample's own skipped source.
const ledgerbase = samples.flatMap((s) => s.plan.sources).find((s) => s.id === 'ledgerbase')!

export function PermittedSources() {
  const ref = useRef<HTMLDivElement>(null)
  const seen = useSeen(ref, 0.25)

  return (
    <Section id="sources" labelledBy="sources-title">
      <Container>
        <SectionHead
          id="sources-title"
          index="06"
          kicker="Permitted sources only"
          title={(s) => (
            <>
              It reads only what it’s <Mark on={s} delay={350}>allowed to read.</Mark>
            </>
          )}
          lede="AWDAX checks robots.txt and sign-in walls before a run. Sources it may not read are skipped, with the reason."
        />

        <div ref={ref} className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-10 md:mt-12 lg:mt-8 lg:grid-cols-12 lg:gap-12">
          <div className="flex flex-col gap-8 lg:col-span-5">
            <figure className="rounded-panel border-2 border-ink bg-surface">
              <figcaption className="border-b-2 border-ink px-4 py-2 font-mono text-micro text-ink-2">{ledgerbase.domain}/robots.txt</figcaption>
              <pre className="px-4 py-3 font-mono text-small text-ink">
                {'User-agent: *\n'}
                <Mark on={seen} delay={400}>
                  Disallow: /companies/
                </Mark>
              </pre>
              <div className="flex flex-col gap-1.5 border-t-2 border-ink px-4 py-3">
                <p className="truncate font-mono text-small text-ink-2">
                  <Strike on={seen} delay={1100}>
                    {ledgerbase.domain}/companies/paisaloop
                  </Strike>
                </p>
                <p className="inline-flex items-start gap-2 text-small text-ink">
                  <BanIcon className="mt-0.5 shrink-0 text-blocked" />
                  Skipped. {ledgerbase.note}
                </p>
              </div>
            </figure>

            <div>
              <h3 className="border-b-2 border-ink pb-2.5 text-small font-semibold text-ink">Ruled out, by design</h3>
              <ul className="flex flex-col">
                {RULED_OUT.map((item, i) => (
                  <li key={item} className="border-b border-line py-2.5 text-h3 font-medium text-ink">
                    <Strike on={seen} delay={1400 + i * 220}>
                      {item}
                    </Strike>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <SourceLedger seen={seen} />
        </div>
      </Container>
    </Section>
  )
}

/** Every source from the four sample runs, two by two: allowed ones by method, the rest struck with the reason. */
function SourceLedger({ seen }: { seen: boolean }) {
  return (
    <div className="grid content-start gap-x-8 gap-y-8 sm:grid-cols-2 lg:col-span-7">
      {samples.map((sample) => (
        <div key={sample.key}>
          <h3 className="flex items-baseline justify-between gap-3 border-b-2 border-ink pb-2.5 text-small font-semibold text-ink">
            {sample.label}
            <span className="font-mono text-micro font-normal text-ink-3">sample run</span>
          </h3>
          <ul>
            {sample.plan.sources.map((s, i) => {
              const skipped = s.permission !== 'allowed'
              return (
                <li
                  key={s.id}
                  title={skipped ? s.note : undefined}
                  className="flex h-9 items-center justify-between gap-3 border-b border-line text-small"
                >
                  <span className="min-w-0 truncate font-mono text-ink">
                    {skipped ? (
                      <Strike on={seen} delay={700 + i * 160} className="text-ink-2">
                        {s.domain}
                      </Strike>
                    ) : (
                      <Mark ink={s.method}>{s.domain}</Mark>
                    )}
                  </span>
                  <span className={`shrink-0 ${skipped ? 'font-semibold text-ink' : 'text-ink-2'}`}>
                    {skipped ? PERMISSION[s.permission] : METHOD[s.method].label}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}
