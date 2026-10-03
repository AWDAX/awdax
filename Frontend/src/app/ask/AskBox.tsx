import { useState } from 'react'
import { parseQuestion } from '../../analytics/ask.ts'
import { askPayload, presentQuery, toEngineQuery } from '../../analytics/askPayload.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { FollowUp } from '../../analytics/suggest.ts'
import { awdax } from '../../api/awdax.ts'
import { ApiError } from '../../api/client.ts'
import type { NewAnswer } from '../chat/answerStore.ts'
import { PromptBox } from '../prompt/PromptBox.tsx'

type Props = {
  profile: TableProfile
  onAnswer: (a: NewAnswer) => void
  /** Offered when a question can't be read, so there's always a next step. */
  suggestions?: FollowUp[]
  placeholder?: string
}

/**
 * Ask the table a question in words, typed or spoken, in the same prompt box as a new chat. A typed question
 * goes to the AI, which plans it against this table's columns: most become an exact query run here in the
 * browser; heavier maths is calculated on the server, in a sandbox, from the rows sent. Nothing re-scrapes, so
 * the chat's data is never reset. The suggestions are written for the exact parser and answer at once; it is
 * also the fallback when the AI can't be reached.
 */
export function AskBox({ profile, onAnswer, suggestions = [], placeholder = 'Ask a follow-up, e.g. “highest price by brand” or “total in 2024”' }: Props) {
  const [text, setText] = useState('')
  const [hint, setHint] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const done = (a: NewAnswer) => {
    setHint(null)
    setText('')
    onAnswer(a)
  }

  /** The exact parser: instant, and the same words always give the same numbers. */
  const askExact = (q: string, otherwise?: string) => {
    const parsed = parseQuestion(profile, q)
    if (parsed.ok) done({ question: q, intent: parsed.intent, chart: parsed.chart, query: parsed.query })
    else setHint(otherwise ?? parsed.hint)
  }

  const ask = async (question: string) => {
    const q = question.trim()
    if (!q || busy) return
    setBusy(true)
    setHint(null)
    try {
      const reply = await awdax.ask({ question: q, ...askPayload(profile) })
      if (reply.kind === 'refuse') setHint(reply.reason)
      else if (reply.kind === 'computed') done({ question: q, computed: { columns: reply.columns, rows: reply.rows, meaning: reply.meaning, basis: profile.rowCount } })
      else {
        const query = toEngineQuery(profile, reply.query)
        if (query) done({ question: q, ...presentQuery(profile, query), query })
        else askExact(q, 'That question doesn’t fit this table’s columns. Try naming a column.')
      }
    } catch (err) {
      // No server at all (0, 502: e.g. an uploaded file with no backend): the exact parser answers, as it always
      // did. The AI being down (503) or anything else is said as it is, with the exact suggestions to pick from:
      // a parser's guess at a question it can't read would be an invented answer.
      if (!(err instanceof ApiError) || [0, 502].includes(err.status)) askExact(q)
      else setHint(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <PromptBox label="Ask about this data" value={text} onChange={setText} onSubmit={(t) => void ask(t)} busy={busy} placeholder={placeholder} />
      {busy && (
        <p role="status" className="text-small text-ink-2">
          Working out the answer from the {profile.rowCount.toLocaleString('en-IN')} rows…
        </p>
      )}
      {hint && (
        <div role="status" className="rounded-control bg-sunken p-3 text-small">
          <p className="text-ink-2">{hint}</p>
          {suggestions.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {suggestions.slice(0, 3).map((s) => (
                <button key={s.id} type="button" onClick={() => askExact(s.text)} className="rounded-control border-2 border-line bg-surface px-2 py-1 text-micro hover:border-ink">
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
