import { useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import type { ChatMessage } from '../../api/types.ts'
import type { LiveState } from '../../api/useLiveStream.ts'
import { profileTable } from '../../analytics/profile.ts'
import { parseRunReport } from '../../analytics/runReport.ts'
import type { DashboardView } from '../dashboard/Dashboard.tsx'
import { buildSources, overlaySources } from '../sources/buildSources.ts'
import type { Visit } from '../sources/buildSources.ts'
import { SourcesPanel } from '../sources/SourcesPanel.tsx'
import { SourcesStrip } from '../sources/SourcesStrip.tsx'
import { TourTrigger } from '../../ui/tour/TourTrigger.tsx'
import { ChatData } from './ChatData.tsx'
import { LiveRun } from './LiveRun.tsx'
import { WORKING } from './phases.ts'
import { Thread } from './Thread.tsx'


type Props = {
  /** Where this chat's dashboard layout and answers are kept. */
  instanceKey: string
  title: string
  meta: ReactNode
  messages: ChatMessage[]
  live: LiveState
  visits: Visit[]
  actions?: ReactNode
  onRetry: () => void
  /** Shown above the title, e.g. "Sample run · fictional data". */
  badge?: ReactNode
}

/**
 * One chat, drawn from plain data (the real page feeds it the backend; the sample run feeds it a script):
 * the request and replies, the live run with the websites being read, then the one-screen dashboard with its
 * Sources tab, and questions about the rows.
 */
export function ChatView({ instanceKey, title, meta, messages, live, visits, actions, onRetry, badge }: Props) {
  const [view, setView] = useState<DashboardView>('report')
  const dashRef = useRef<HTMLDivElement>(null)
  const working = live.liveEnabled && WORKING.includes(live.status.phase ?? 'idle')
  const table = live.dataset && live.dataset.rows.length > 0 ? live.dataset : null
  const report = useMemo(() => {
    for (const m of messages) if (m.role === 'bot') { const r = parseRunReport(m.text); if (r) return r }
    return null
  }, [messages])
  const profile = useMemo(() => (table ? profileTable(table) : undefined), [table])
  const remote = instanceKey !== 'sample-run'
  const sources = useMemo(
    () => overlaySources(buildSources({ report, profile, visits, current: live.status.current_source, working }), remote ? live.sources : undefined),
    [report, profile, visits, live.status.current_source, live.sources, working, remote],
  )
  const panel = <SourcesPanel sources={sources} report={report} visits={visits} />
  const openSources = () => {
    setView('sources')
    dashRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (

    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-6">
      <header data-tour="chat-header" className="flex flex-wrap items-start gap-3 border-b-2 border-ink pb-4">
        <div className="min-w-0 flex-1">
          {badge}
          <h1 className="font-display font-wide text-h3 font-extrabold break-words">{title}</h1>
          <p className="mt-1 font-mono text-micro text-ink-3">{meta}</p>
        </div>
        {/* Equal boxes: every action is the same height, and on wider screens the same width (the widest one's),
            so the row reads as one set; on phones they stack full width. */}
        <div className="flex flex-wrap items-center gap-2">
          <TourTrigger tourId="chat-view-tour" label="Session Tour" variant="secondary" />
          {actions && <div className="grid w-full grid-cols-1 gap-2 *:w-full *:justify-center sm:w-auto sm:auto-cols-fr sm:grid-flow-col sm:grid-cols-none">{actions}</div>}
        </div>
      </header>

      <div data-tour="chat-thread" className="max-w-3xl">
        <Thread messages={messages} working={working} />
      </div>
      <div data-tour="chat-liverun">
        <LiveRun live={live} onRetry={onRetry} footer={sources.length > 0 ? <SourcesStrip sources={sources} onOpen={table ? openSources : undefined} /> : undefined} />
      </div>

      {table ? (
        <div ref={dashRef} data-tour="chat-data-view" className="scroll-mt-4">
          <ChatData
            instanceId={instanceKey}
            table={table}
            title={title}
            sources={{ count: sources.filter((s) => s.state !== 'rejected').length, panel }}
            view={view}
            onViewChange={setView}
            remote={remote}
            graphTick={live.graphTick}
            stats={live.stats}
            includePartial={live.includePartial}
            onIncludePartial={live.setIncludePartial}
            onRefresh={live.refresh}
          />
        </div>
      ) : (
        <>
          {sources.length > 0 && <div data-tour="chat-sources-tab">{panel}</div>}
          <div className="grid min-h-40 place-items-center rounded-panel border-2 border-dashed border-line-strong p-8 text-center text-ink-2">
            <p className="max-w-[46ch]">Your dashboard appears here after the first pass. Charts, filters and questions all work from the rows AWDAX finds.</p>
          </div>
        </>
      )}
    </div>
  )
}

