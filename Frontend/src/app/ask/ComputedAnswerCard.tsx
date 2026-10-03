import type { TableProfile } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import { TrashIcon } from '../../ui/appIcons.tsx'
import { AssistantOrb } from '../../ui/micro/AssistantOrb.tsx'
import { CopyButton } from '../../ui/micro/CopyButton.tsx'
import type { ComputedAnswer, ComputedResult } from '../chat/answerStore.ts'
import { ResultTable } from './ResultTable.tsx'

const action = 'inline-flex h-7 items-center gap-1.5 rounded-control px-2 text-micro text-ink-2 hover:bg-sunken hover:text-ink'

/** Tab-separated, header first: pastes into a spreadsheet as a table. */
const tsv = (c: ComputedResult) =>
  [c.columns.map((x) => x.name), ...c.rows.map((r) => r.map((v) => (v === null ? '' : String(v))))].map((r) => r.join('\t')).join('\n')

/**
 * An answer that needed more than one aggregate (growth, ratios, spread), calculated on the server: what it means,
 * then the result with its schema. Its numbers are a snapshot of the rows it was given, so it says when the table
 * has changed since.
 */
export function ComputedAnswerCard({ profile, saved, onRemove }: { profile: TableProfile; saved: ComputedAnswer; onRemove?: () => void }) {
  const c = saved.computed
  const changed = c.basis !== profile.rowCount || (saved.signature !== undefined && saved.signature !== columnSignature(profile))
  return (
    <article className="flex flex-col gap-3">
      <p className="ml-auto max-w-[85%] rounded-panel border-2 border-ink bg-signal-soft px-3 py-2 text-small">{saved.question}</p>
      <div className="flex gap-3">
        <AssistantOrb size="md" className="mt-0.5 shrink-0" />
        <div className="min-w-0 flex-1 rounded-panel border-2 border-ink p-4">
          <p className="text-lead font-medium">{c.meaning || 'Calculated from the table.'}</p>
          <div className="mt-3">
            <ResultTable columns={c.columns} rows={c.rows} caption={saved.question} />
          </div>
          <p className="mt-3 border-t border-line pt-2 text-micro text-ink-3">
            Calculated from {c.basis.toLocaleString('en-IN')} rows.
            {changed && ' The table has changed since; ask again for current numbers.'}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-1">
            <CopyButton text={() => `${c.meaning}\n\n${tsv(c)}`} label="Copy the answer" />
            {onRemove && (
              <button type="button" onClick={onRemove} className={`${action} ml-auto hover:text-blocked`} aria-label="Remove this answer">
                <TrashIcon />
              </button>
            )}
          </div>
        </div>
      </div>
    </article>
  )
}
