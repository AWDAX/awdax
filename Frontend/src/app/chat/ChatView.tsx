import { useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { AnimatePresence, m } from 'motion/react'
import { EASE_SOFT } from '../../ui/motion.ts'
import type { ChatMessage } from '../../api/types.ts'
import type { LiveState } from '../../api/useLiveStream.ts'
import { profileTable } from '../../analytics/profile.ts'
import { parseRunReport } from '../../analytics/runReport.ts'
import type { DashboardView } from '../dashboard/Dashboard.tsx'
import { buildSources, overlaySources } from '../sources/buildSources.ts'
import type { Visit } from '../sources/buildSources.ts'
import { SourcesPanel } from '../sources/SourcesPanel.tsx'
import { SourcesStrip } from '../sources/SourcesStrip.tsx'
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
  /** Recorded or scripted data (a demo replay): nothing is asked of the backend, so no rescoring. */
  offline?: boolean
}

/**
 * One chat, drawn from plain data (the real page feeds it the backend; the sample run feeds it a script):
 * the request and replies, the live run with the websites being read, then the one-screen dashboard with its
 * Sources tab, and questions about the rows.
 */
export function ChatView({ instanceKey, title, meta, messages, live, visits, actions, onRetry, badge, offline = false }: Props) {
  const [view, setView] = useState<DashboardView>('report')
  const dashRef = useRef<HTMLDivElement>(null)
  const working = live.liveEnabled && WORKING.includes(live.status.phase ?? 'idle')
  const table = live.dataset && live.dataset.rows.length > 0 ? live.dataset : null
  const report = useMemo(() => {
    for (const m of messages) if (m.role === 'bot') { const r = parseRunReport(m.text); if (r) return r }
    return null
  }, [messages])
  const profile = useMemo(() => (table ? profileTable(table) : undefined), [table])
  const remote = !offline && instanceKey !== 'sample-run'
  // The scripted sample run has no source list (an empty one changes nothing); a recorded replay has the real one.
  const sources = useMemo(
    () => overlaySources(buildSources({ report, profile, visits, current: live.status.current_source, working }), live.sources),
    [report, profile, visits, live.status.current_source, live.sources, working],
  )
  const panel = <SourcesPanel sources={sources} report={report} visits={visits} />
  const openSources = () => {
    setView('sources')
    dashRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  // Before there is a dashboard, the full source list stays folded away under the strip's Details.
  const [showPanel, setShowPanel] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)
  const toggleSources = () => {
    if (table) return openSources()
    setShowPanel(!showPanel)
    // Opening brings the list into view; closing leaves the scroll alone.
    if (!showPanel) requestAnimationFrame(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }))
  }

  return (

    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-6">
      <header className="flex flex-wrap items-start gap-3 border-b-2 border-ink pb-4">
        <div className="min-w-0 flex-1">
          {badge}
          <h1 className="font-display font-wide text-h3 font-extrabold break-words">{title}</h1>
          <p className="mt-1 font-mono text-micro text-ink-3">{meta}</p>
        </div>
        {/* Equal boxes: every action is the same height, and on wider screens the same width (the widest one's),
            so the row reads as one set; on phones they stack full width. A real chat has one ⋯ menu here (the
            tutorial is in it and on the sidebar's compass). */}
        {actions && <div className="grid w-full grid-cols-1 gap-2 *:w-full *:justify-center sm:w-auto sm:auto-cols-fr sm:grid-flow-col sm:grid-cols-none">{actions}</div>}
      </header>

      {/* Full width, like a chat: the user's messages sit on the right edge, the replies on the left. A narrower
          column here put the user's bubble in the middle of the page. */}
      <Thread messages={messages} working={working} />
      <div>
        <LiveRun live={live} onRetry={onRetry} footer={sources.length > 0 ? <SourcesStrip sources={sources} onOpen={toggleSources} open={!table && showPanel} /> : undefined} />
      </div>

      {table ? (
        <div ref={dashRef} className="scroll-mt-4">
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
          <AnimatePresence initial={false}>
            {sources.length > 0 && showPanel && (
              <m.div
                ref={panelRef}
                key="sources"
                className="scroll-mt-4"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.45, ease: EASE_SOFT }}
              >
                {panel}
              </m.div>
            )}
          </AnimatePresence>
          <div className="grid min-h-40 place-items-center rounded-panel border-2 border-dashed border-line-strong p-8 text-center text-ink-2">
            <p className="max-w-[46ch]">Your dashboard appears here after the first pass. Charts, filters and questions all work from the rows AWDAX finds.</p>
          </div>
        </>
      )}
    </div>
  )
}

