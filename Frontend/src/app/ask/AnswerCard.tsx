import { useMemo, useState } from 'react'
import { answer, STALE_MESSAGE } from '../../analytics/answer.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { ChartSpec } from '../../analytics/spec.ts'
import { ChartIcon, DownloadIcon, TrashIcon } from '../../ui/appIcons.tsx'
import { AssistantOrb } from '../../ui/micro/AssistantOrb.tsx'
import { CopyButton } from '../../ui/micro/CopyButton.tsx'
import { isStaleAnswer } from '../chat/answerStore.ts'
import type { SavedAnswer } from '../chat/useAnswers.ts'
import { ChartView } from '../dashboard/charts/ChartView.tsx'
import { PrecisionNote } from '../dashboard/PrecisionNote.tsx'
import { ExportDialog } from '../export/ExportDialog.tsx'

type Props = {
  profile: TableProfile
  saved: SavedAnswer
  /** Used in export file names. */
  title: string
  onAddToDashboard?: (spec: ChartSpec) => void
  onRemove?: () => void
}

const action = 'inline-flex h-7 items-center gap-1.5 rounded-control px-2 text-micro text-ink-2 hover:bg-sunken hover:text-ink'

/** One question answered from the table, or, when its columns are gone, a note saying so (and the way to remove it). */
export function AnswerCard(props: Props) {
  return isStaleAnswer(props.saved, props.profile) ? <StaleAnswer saved={props.saved} onRemove={props.onRemove} /> : <LiveAnswer {...props} />
}

/** Kept, not deleted: the table may get its columns back, and only the user decides to drop a question. */
function StaleAnswer({ saved, onRemove }: Pick<Props, 'saved' | 'onRemove'>) {
  return (
    <article className="flex flex-col gap-3">
      <p className="ml-auto max-w-[85%] rounded-panel border-2 border-ink bg-signal-soft px-3 py-2 text-small">{saved.question}</p>
      <div className="flex gap-3">
        <AssistantOrb size="md" className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1 rounded-panel border-2 border-line p-4">
          <p role="status" className="text-small text-ink-2">
            {STALE_MESSAGE} The table's columns changed since you asked. Ask again to get a current answer.
          </p>
          {onRemove && (
            <div className="mt-2 flex">
              <button type="button" onClick={onRemove} className={`${action} ml-auto hover:text-blocked`} aria-label="Remove this answer">
                <TrashIcon />
              </button>
            </div>
          )}
        </div>
      </div>
    </article>
  )
}

/** One question answered from the table: the exact sentence, a small chart, what was counted, and actions. */
function LiveAnswer({ profile, saved, title, onAddToDashboard, onRemove }: Props) {
  const a = useMemo(() => answer(profile, saved.question, saved.intent, saved.query, saved.chart), [profile, saved])
  const [exporting, setExporting] = useState(false)
  const [added, setAdded] = useState(false)
  const spec: ChartSpec = { id: saved.id, type: saved.chart, title: saved.question, reason: 'Pinned from a question.', query: saved.query }
  // "Which is highest?" answers with one group; on the dashboard it's more useful as the whole ranking.
  const pinned: ChartSpec =
    saved.query.limit === 1 && saved.query.groupBy !== undefined
      ? { ...spec, query: { ...saved.query, limit: undefined, other: undefined }, labels: true }
      : spec
  const grouped = saved.query.groupBy !== undefined && a.result.rows.length > 1

  return (
    <article className="flex flex-col gap-3">
      <p className="ml-auto max-w-[85%] rounded-panel border-2 border-ink bg-signal-soft px-3 py-2 text-small">{saved.question}</p>
      <div className="flex gap-3">
        <AssistantOrb size="md" className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1 rounded-panel border-2 border-ink p-4">
          <p className="text-lead font-medium">{a.sentence}</p>
          {grouped && (
            <div className="mt-3">
              <ChartView spec={{ ...spec, type: saved.chart === 'kpi' ? 'bar' : saved.chart }} profile={profile} height={200} />
            </div>
          )}
          <div className="mt-3 border-t border-line pt-2">
            <PrecisionNote profile={profile} result={a.result} />
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {onAddToDashboard && (
              <button
                type="button"
                disabled={added}
                onClick={() => {
                  onAddToDashboard(pinned)
                  setAdded(true)
                }}
                className={`${action} disabled:text-ink-3`}
              >
                <ChartIcon /> {added ? 'On the dashboard' : 'Add to dashboard'}
              </button>
            )}
            <button type="button" onClick={() => setExporting(true)} className={action}>
              <DownloadIcon /> Export numbers
            </button>
            <CopyButton text={a.sentence} label="Copy the answer" />
            {onRemove && (
              <button type="button" onClick={onRemove} className={`${action} ml-auto hover:text-blocked`} aria-label="Remove this answer">
                <TrashIcon />
              </button>
            )}
          </div>
        </div>
      </div>
      {exporting && <ExportDialog profile={profile} scope={{ kind: 'answer', answer: a, label: saved.question }} title={title} onClose={() => setExporting(false)} />}
    </article>
  )
}
