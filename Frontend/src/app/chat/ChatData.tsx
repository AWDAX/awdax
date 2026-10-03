import { useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { awdax } from '../../api/awdax.ts'
import type { DatasetStats, DatasetTable } from '../../api/types.ts'
import { profileTable } from '../../analytics/profile.ts'
import { suggestFollowUps } from '../../analytics/suggest.ts'
import { AnswerCard } from '../ask/AnswerCard.tsx'
import { AskBox } from '../ask/AskBox.tsx'
import { Dashboard } from '../dashboard/Dashboard.tsx'
import type { DashboardView } from '../dashboard/Dashboard.tsx'
import { useDashboard } from '../dashboard/useDashboard.ts'
import { GraphsPanel } from '../graphs/GraphsPanel.tsx'
import { ScoreSummary } from '../scoring/Scoring.tsx'
import { FollowUps } from './FollowUps.tsx'
import { useAnswers } from './useAnswers.ts'

type Props = {
  instanceId: string
  table: DatasetTable
  title: string
  sources?: { count: number; panel: ReactNode }
  view?: DashboardView
  onViewChange?: (v: DashboardView) => void
  /** Real AwdaxP chat (the sample run leaves this off). */
  remote?: boolean
  graphTick?: number
  stats?: DatasetStats | null
  includePartial?: boolean
  onIncludePartial?: (value: boolean) => void
  onRefresh?: () => Promise<void> | void
}

/**
 * Everything built from a chat's scraped table: the dashboard, then questions about it (follow-up chips, the
 * Ask box, and the answers so far). Mounted only once the table exists, so the hooks always have data.
 */
export function ChatData({ instanceId, table, title, sources, view, onViewChange, remote, stats = null, includePartial, onIncludePartial, onRefresh }: Props) {
  const profile = useMemo(() => profileTable(table), [table])
  const dash = useDashboard(instanceId, profile)
  const answers = useAnswers(instanceId, profile)
  const followUps = useMemo(() => suggestFollowUps(profile), [profile])
  const asked = new Set(answers.items.map((a) => a.question))
  const fresh = followUps.filter((f) => !asked.has(f.text))
  const last = useRef<HTMLLIElement>(null)
  const count = answers.items.length
  const firstRender = useRef(true)

  // A new answer scrolls into view; answers restored on load don't.
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false
      return
    }
    last.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [count])

  return (
    <>
      <Dashboard
        profile={profile}
        dash={dash}
        title={title}
        sources={sources}
        view={view}
        onViewChange={onViewChange}
        records={remote ? table.records : undefined}
        graphs={<GraphsPanel key={instanceId} instanceId={instanceId} profile={profile} includePartial={includePartial} onIncludePartial={onIncludePartial} />}
        scoring={remote ? (
          <ScoreSummary
            stats={stats}
            includePartial={includePartial}
            onIncludePartial={onIncludePartial}
            onRescore={onRefresh ? async () => {
              await awdax.rescore(instanceId)
              await onRefresh()
            } : undefined}
          />
        ) : undefined}
      />
      {/* A full-width rule closes the dashboard. On wide screens the questions to ask sit in a left column beside
          the answers and the box, so the section uses the page's width instead of leaving it empty on the right. */}
      <section aria-labelledby="ask-heading" className="mt-4 grid gap-x-10 gap-y-6 border-t-2 border-ink pt-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <div className="flex flex-col gap-5 lg:sticky lg:top-6 lg:self-start">
          <div>
            <h2 id="ask-heading" className="font-display text-h3 font-extrabold">
              Ask about this data
            </h2>
            <p className="mt-1 text-small text-ink-2">
              Answered from the {profile.rowCount.toLocaleString('en-IN')} rows above, exactly. Asking never re-scrapes; for new data, start a new chat.
            </p>
          </div>
          <FollowUps items={fresh} onPick={(f) => answers.add({ question: f.text, intent: f.intent, chart: f.chart, query: f.query })} />
        </div>
        <div className="flex min-w-0 flex-col gap-6">
          {answers.items.length > 0 && (
            <ol className="flex flex-col gap-6">
              {answers.items.map((a, i) => (
                <li key={a.id} ref={i === answers.items.length - 1 ? last : undefined}>
                  <AnswerCard profile={profile} saved={a} title={title} onAddToDashboard={dash.add} onRemove={() => answers.remove(a.id)} />
                </li>
              ))}
            </ol>
          )}
          {/* Pinned to the bottom of the chat while answers are on screen (they scroll under it), like ChatGPT's
              composer; with no answers yet it sits at the top of its column, level with the heading. */}
          <div className="sticky bottom-0 z-10 -mx-1 bg-canvas px-1 pt-2 pb-4">
            <span aria-hidden className="pointer-events-none absolute inset-x-0 -top-6 h-6 bg-linear-to-b from-transparent to-canvas" />
            <AskBox profile={profile} onAnswer={answers.add} suggestions={followUps} />
          </div>
          {answers.items.length === 0 && (
            <p className="-mt-4 rounded-panel border-2 border-dashed border-line px-6 py-10 text-center text-small text-ink-3">
              Answers show up here, each with its own chart. Pick a question on the left or type your own.
            </p>
          )}
        </div>
      </section>
    </>
  )
}
