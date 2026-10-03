import { useState } from 'react'
import { Container } from '../../ui/Container.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { Section, SectionHead } from '../SectionHead.tsx'

// Every answer describes what the app and backend do today (checked against the code on 2026-09-28, see
// docs/APP.md and docs/PRODUCT.md). Change them together; don't promise a feature before it ships.
const FAQ = [
  {
    q: 'What kind of data can I ask for?',
    a: 'Lists of things published on the web: sales by month, job openings, companies and their funding, product prices. Describe the rows you want in a sentence, or drop in a CSV, Excel or JSON file you already have. AWDAX picks the columns and builds a dashboard from the rows.',
  },
  {
    q: 'Which websites does AWDAX read?',
    a: 'It searches for sources, inspects each one and keeps the ones it can read. Pages behind a sign-in, a block or a CAPTCHA are rejected, never worked around. The Sources tab lists every site it used and every site it rejected, with the reason.',
  },
  {
    q: 'What happens when a value isn’t on the page?',
    a: 'The cell stays empty and reads “Not found”. Nothing is guessed or filled in. Charts count only the values that exist and say which rows they left out, and why.',
  },
  {
    q: 'What if two sources disagree?',
    a: 'Both figures stay. Every row keeps the website it came from, so a number two sites report differently appears once for each. Filter the dashboard by source to compare them side by side.',
  },
  {
    q: 'How do I know where a value came from?',
    a: 'Every row keeps its website and page address. The Sources tab shows each site with how it was read, how many rows it gave and how complete they were, and lists the sites that were rejected and why.',
  },
  {
    q: 'Can I keep a dataset up to date?',
    a: 'Yes. A web request keeps running: AWDAX re-checks its sources every five minutes by default, updates rows that changed and adds new ones without duplicates. Pause it at any time, and turn on alerts to hear about new rows.',
  },
  {
    q: 'What can I do with the result?',
    a: 'Shape it into a dashboard that fits one screen: pick from suggested charts or build your own, then resize, move and filter them. Ask questions in plain words for exact answers, and export the data as SQL, Excel, CSV, JSON and more.',
  },
  {
    q: 'Is AWDAX a BI tool?',
    a: 'Partly. Every dataset gets a dashboard you can shape, and questions are answered exactly from its rows. For joins across datasets and deeper modelling, export it to SQL, Excel or Power BI.',
  },
  {
    q: 'Is the data on this page real?',
    a: 'No. The sample runs use fictional companies on .example domains, so nothing here can be mistaken for a real company’s data.',
  },
]

export function Faq() {
  return (
    <Section id="faq" labelledBy="faq-title">
      <Container className="grid grid-cols-[minmax(0,1fr)] gap-10 lg:grid-cols-12 lg:gap-12">
        <SectionHead
          id="faq-title"
          index="07"
          kicker="Questions"
          layout="stack"
          className="self-start lg:sticky lg:top-24 lg:col-span-4"
          title={(s) => (
            <>
              Asked, and <Mark on={s} delay={350}>answered plainly.</Mark>
            </>
          )}
          lede="Still unsure? Every answer here is how AWDAX is built to behave."
        />

        <div className="border-b-2 border-ink lg:col-span-8">
          {FAQ.map((item) => (
            <FaqItem key={item.q} q={item.q} a={item.a} />
          ))}
        </div>
      </Container>
    </Section>
  )
}

function FaqItem({ q, a }: { q: string; a: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="group border-t-2 border-ink">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full cursor-pointer list-none items-baseline justify-between gap-6 py-4 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
      >
        <span className="text-h3 font-bold text-ink">
          <Mark on={open} className="group-hover:mark-on">
            {q}
          </Mark>
        </span>
        <span aria-hidden className="font-mono text-h3 text-ink select-none">
          {open ? '−' : '+'}
        </span>
      </button>
      <div
        className={`grid transition-[grid-template-rows,opacity] duration-300 ease-soft ${
          open ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className="overflow-hidden">
          <p className="max-w-[62ch] pb-5 text-body text-ink-2 leading-relaxed">{a}</p>
        </div>
      </div>
    </div>
  )
}

