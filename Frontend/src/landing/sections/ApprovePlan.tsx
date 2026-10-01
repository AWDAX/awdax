import { sampleByKey } from '../../domain/fixtures/index.ts'
import { PlanEditor } from '../../product/PlanEditor.tsx'
import { Container } from '../../ui/Container.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Section, SectionHead } from '../SectionHead.tsx'

const POINTS = [
  { title: 'Columns and their types', body: 'Keep what you need, drop the rest. Required columns stay.' },
  { title: 'How unclear words were read', body: 'AWDAX says which reading it chose and offers the others.' },
  { title: 'Sources, with permission', body: 'The ones it may not read are listed with the reason.' },
]

export function ApprovePlan() {
  return (
    <Section labelledBy="plan-title">
      <Container data-tour="landing-plan">
        <SectionHead
          id="plan-title"
          index="02"
          kicker="You approve the plan"
          title={(seen) => (
            <>
              Nothing runs until you <Mark on={seen} delay={350}>approve the plan.</Mark>
            </>
          )}
          lede="Before AWDAX reads a page, it writes down what it will collect and from where. Change any of it."
        />

        <div className="mt-10 grid grid-cols-[minmax(0,1fr)] gap-10 md:mt-12 lg:mt-8 lg:grid-cols-12 lg:gap-12">
          <div className="flex flex-col justify-center gap-8 lg:col-span-4">
            <ol className="flex flex-col gap-6">
              {POINTS.map((p, i) => (
                <li key={p.title} className="grid grid-cols-[2.25rem_minmax(0,1fr)] gap-x-2">
                  <span className="pt-0.5 font-mono text-small text-ink-3">{String(i + 1).padStart(2, '0')}</span>
                  <div>
                    <h3 className="text-h3 font-bold text-ink">{p.title}</h3>
                    <p className="mt-1.5 max-w-[36ch] text-body text-ink-2">{p.body}</p>
                  </div>
                </li>
              ))}
            </ol>
            <p className="pl-11 text-small text-ink-3">
              Sample run: {sampleByKey.jobs.label}. Every control on this plan works.
            </p>
          </div>

          <div className="lg:col-span-8">
            <PlanEditor plan={sampleByKey.jobs.plan} density="compact" />
          </div>
        </div>
      </Container>
    </Section>
  )
}
