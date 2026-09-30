import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Container } from '../../ui/Container.tsx'
import { ArrowIcon } from '../../ui/icons.tsx'

/** The last word: a full-width yellow band with the request field. Submitting opens the workspace. */
export function FinalCta() {
  const navigate = useNavigate()
  const [text, setText] = useState('')

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const q = text.trim()
    navigate(q ? `/app?q=${encodeURIComponent(q)}` : '/app')
  }

  return (
    <section aria-labelledby="cta-title" className="border-y-2 border-ink bg-signal">
      <Container className="py-16 md:py-24">
        <h2 id="cta-title" className="max-w-[16ch] font-display font-wide text-display font-extrabold text-ink">
          Describe the data you need.
        </h2>
        <form onSubmit={submit} className="mt-10 flex flex-col gap-3 md:mt-12 md:flex-row">
          <label htmlFor="cta-request" className="sr-only">
            Describe the data you need
          </label>
          <input
            id="cta-request"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Seed-stage fintech startups in India funded in 2026"
            autoComplete="off"
            className="h-14 min-w-0 flex-1 rounded-control border-2 border-ink bg-surface px-4 text-h3 text-ink placeholder:text-ink-3 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink"
          />
          <button
            type="submit"
            className="inline-flex h-14 shrink-0 items-center justify-center gap-2 rounded-control border-2 border-ink bg-ink px-6 text-body font-semibold text-signal transition-[background-color,color,scale] duration-150 hover:bg-surface hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink active:scale-97"
          >
            Plan it <ArrowIcon />
          </button>
        </form>
        <p className="mt-4 text-small text-ink">Opens the workspace. Nothing runs until you approve the plan.</p>
      </Container>
    </section>
  )
}
