import { timeAgo } from '../../api/dates.ts'
import type { ChatMessage } from '../../api/types.ts'
import { AssistantOrb } from '../../ui/micro/AssistantOrb.tsx'
import { CopyButton } from '../../ui/micro/CopyButton.tsx'
import { withoutMasterTable } from '../../analytics/runReport.ts'
import { Markdown } from './Markdown.tsx'

/** A bot reply. The run report's copy of every row is cut: the rows are in the dashboard, exactly. */
function BotText({ text }: { text: string }) {
  const { text: body, removedRows } = withoutMasterTable(text)
  return (
    <>
      <Markdown text={body} />
      {removedRows !== null && (
        <p className="mt-2 text-small text-ink-2">
          The {removedRows.toLocaleString('en-IN')} rows are in the dashboard below, with their sources in its Sources tab.
        </p>
      )}
    </>
  )
}

/** The request and the backend's replies, oldest first. The newest reply "breathes" while a run is working. */
export function Thread({ messages, working }: { messages: ChatMessage[]; working: boolean }) {
  const lastBot = [...messages].reverse().find((m) => m.role === 'bot')?.id
  return (
    <ol className="flex flex-col gap-5">
      {messages.map((m) =>
        m.role === 'user' ? (
          <li key={m.id} className="ml-auto max-w-[min(85%,42rem)] rounded-panel border-2 border-ink bg-signal-soft px-4 py-3">
            <p className="text-body break-words whitespace-pre-wrap">{m.text}</p>
            <p className="mt-1 text-right font-mono text-micro text-ink-3">{timeAgo(m.created_at)}</p>
          </li>
        ) : (
          // Replies keep a reading width on the left, so the thread spans the page without long lines.
          <li key={m.id} className="group flex max-w-3xl gap-3">
            <AssistantOrb size="md" working={working && m.id === lastBot} className="mt-0.5 shrink-0" />
            <div className="min-w-0 flex-1">
              <BotText text={m.text} />
              <div className="mt-1 flex items-center gap-2 font-mono text-micro text-ink-3">
                {timeAgo(m.created_at)}
                <CopyButton text={m.text} label="Copy this reply" className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100" />
              </div>
            </div>
          </li>
        ),
      )}
    </ol>
  )
}
