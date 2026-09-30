import { useState } from 'react'
import { parseQuestion } from '../../analytics/ask.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { FollowUp } from '../../analytics/suggest.ts'
import type { SavedAnswer } from '../chat/useAnswers.ts'
import { PromptBox } from '../prompt/PromptBox.tsx'

type Props = {
  profile: TableProfile
  onAnswer: (a: Omit<SavedAnswer, 'id' | 'createdAt'>) => void
  /** Offered when a question can't be read, so there's always a next step. */
  suggestions?: FollowUp[]
  placeholder?: string
}

/**
 * Ask the table a question in words, typed or spoken, in the same prompt box as a new chat. Answered in the
 * browser, exactly; nothing goes to the backend, so the chat's data is never reset. A question it can't read
 * says so and offers ones it can.
 */
export function AskBox({ profile, onAnswer, suggestions = [], placeholder = 'Ask a follow-up, e.g. “highest price by brand” or “total in 2024”' }: Props) {
  const [text, setText] = useState('')
  const [hint, setHint] = useState<string | null>(null)

  const ask = (question: string) => {
    const q = question.trim()
    if (!q) return
    const parsed = parseQuestion(profile, q)
    if (!parsed.ok) {
      setHint(parsed.hint)
      return
    }
    setHint(null)
    setText('')
    onAnswer({ question: q, intent: parsed.intent, chart: parsed.chart, query: parsed.query })
  }

  return (
    <div className="flex flex-col gap-2">
      <PromptBox label="Ask about this data" value={text} onChange={setText} onSubmit={(t) => ask(t)} placeholder={placeholder} />
      {hint && (
        <div role="status" className="rounded-control bg-sunken p-3 text-small">
          <p className="text-ink-2">{hint}</p>
          {suggestions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.slice(0, 3).map((s) => (
                <button key={s.id} type="button" onClick={() => ask(s.text)} className="rounded-control border-2 border-line bg-surface px-2 py-1 text-micro hover:border-ink">
                  {s.text}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
