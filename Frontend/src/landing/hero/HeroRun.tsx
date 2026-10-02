import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, m, useInView, useReducedMotion } from 'motion/react'
import { chartFor } from '../../domain/charts.ts'
import { samples } from '../../domain/fixtures/index.ts'
import type { SampleRun } from '../../domain/fixtures/index.ts'
import type { Column } from '../../domain/types.ts'
import { AutoChart } from '../../product/AutoChart.tsx'
import { PlanCard } from '../../product/PlanCard.tsx'
import { RowStream } from '../../product/RowStream.tsx'
import { MethodLegend } from '../../product/SourceChip.tsx'
import { buttonClass } from '../../ui/buttonClass.ts'
import { PauseIcon, PlayIcon, ReplayIcon } from '../../ui/icons.tsx'
import { Mark } from '../../ui/Mark.tsx'
import { EASE_SOFT } from '../../ui/motion.ts'
import { RequestBar } from './RequestBar.tsx'
import { SourcePage } from './SourcePage.tsx'
import { StepRail } from './StepRail.tsx'
import { DETAILED_ROWS, frameAt, sameFrame, scheduleFor } from './timeline.ts'
import { TraceLayer } from './TraceLayer.tsx'
import { useTimeline } from './useTimeline.ts'

const HOLD_MS = 4500
const SWAP = { duration: 0.45, ease: EASE_SOFT }

/**
 * The hero's live sample run: a request types itself, the plan appears and is approved, then the
 * first rows are read one source page at a time, each value traced to its cell, before the rest
 * stream in. The cleaning summary lands and the chart fills in. It moves on to the next sample by
 * itself until the visitor takes control.
 */
export function HeroRun() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { amount: 0.25 })
  const reduced = useReducedMotion() ?? false
  const [index, setIndex] = useState(0)
  const [take, setTake] = useState(0)
  const [autoAdvance, setAutoAdvance] = useState(!reduced)

  const next = useCallback(() => setIndex((i) => (i + 1) % samples.length), [])
  const takeControl = useCallback(() => setAutoAdvance(false), [])
  const choose = (i: number) => {
    setAutoAdvance(false)
    setIndex(i)
    setTake((n) => n + 1)
  }

  return (
    <div ref={ref} className="flex flex-col gap-5">
      <RunPanel
        key={`${samples[index].key}-${take}`}
        sample={samples[index]}
        active={inView}
        autoAdvance={autoAdvance}
        onNext={next}
        onTakeControl={takeControl}
      />
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
        <span className="text-small text-ink-3">Replay with</span>
        {samples.map((s, i) => (
          <button
            key={s.key}
            type="button"
            aria-pressed={i === index}
            onClick={() => choose(i)}
            className="group rounded-control text-small font-semibold text-ink focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink"
          >
            <Mark on={i === index} className="group-hover:mark-on">
              {s.label}
            </Mark>
          </button>
        ))}
      </div>
    </div>
  )
}

type PanelProps = {
  sample: SampleRun
  active: boolean
  autoAdvance: boolean
  onNext: () => void
  onTakeControl: () => void
}

function RunPanel({ sample, active, autoAdvance, onNext, onTakeControl }: PanelProps) {
  const sceneRef = useRef<HTMLDivElement>(null)
  const sch = useMemo(() => scheduleFor(sample), [sample])
  const at = useCallback((t: number) => frameAt(sample, sch, t), [sample, sch])
  const { frame, playing, finished, pause, play } = useTimeline(sch.useAt, at, sameFrame, active)

  useEffect(() => {
    if (!finished || !autoAdvance || !active) return
    const id = setTimeout(onNext, HOLD_MS)
    return () => clearTimeout(id)
  }, [finished, autoAdvance, active, onNext])

  const { dataset, plan, request } = sample
  const shownRows = useMemo(() => dataset.rows.slice(0, frame.rowsShown), [dataset.rows, frame.rowsShown])
  const chartColumn = dataset.columns.find((c) => c.key === sample.heroChart)
  const spec = useMemo(
    () => (chartColumn ? chartFor(chartColumn, shownRows, dataset.rows) : null),
    [chartColumn, shownRows, dataset.rows],
  )
  // defineSample has already checked these keys exist, so find() cannot miss.
  const col = (key: string) => dataset.columns.find((c) => c.key === key)!
  const [a, b, c] = sample.streamColumns
  const streamColumns: [Column, Column, Column] = [col(a), col(b), col(c)]

  // While the first rows are read, the page being read takes the plan's place.
  const pageRow = frame.reading > 0 && frame.rowsShown <= DETAILED_ROWS ? dataset.rows[frame.reading - 1] : null
  const pageSource = pageRow && plan.sources.find((s) => s.id === pageRow.sourceIds[0])
  const traceRow = pageRow && frame.rowsShown >= frame.reading ? pageRow.id : null

  const toggle = () => {
    onTakeControl()
    if (playing) pause()
    else play()
  }

  return (
    <div className="border-y-2 border-ink">
      <div className="flex h-14 items-center justify-between gap-3 border-b border-line">
        <StepRail phase={frame.phase} />
        <div className="flex items-center gap-2">
          <span className="font-mono text-micro text-ink-2">Sample run</span>
          <button
            type="button"
            onClick={toggle}
            aria-label={playing ? 'Pause the sample run' : finished ? 'Replay the sample run' : 'Play the sample run'}
            className={buttonClass('ghost', 'md', 'w-10 px-0! sm:w-auto sm:px-3!')}
          >
            {playing ? <PauseIcon /> : finished ? <ReplayIcon /> : <PlayIcon />}
            <span aria-hidden className="hidden sm:inline">
              {playing ? 'Pause' : finished ? 'Replay' : 'Play'}
            </span>
          </button>
        </div>
      </div>

      <RequestBar text={request.text} typed={frame.typed} sent={frame.phase !== 'ask'} />

      <div
        ref={sceneRef}
        className="relative grid gap-8 py-6 sm:py-8 lg:grid-cols-[minmax(0,5fr)_4.5rem_minmax(0,7fr)] lg:gap-0"
      >
        <div className="min-w-0">
          <AnimatePresence mode="wait" initial={false}>
            <m.div
              key={pageRow ? pageRow.id : 'plan'}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={SWAP}
            >
              {pageRow && pageSource ? (
                <SourcePage row={pageRow} source={pageSource} columns={dataset.columns} traced={sample.streamColumns} />
              ) : (
                <PlanCard
                  plan={plan}
                  density="compact"
                  revealed={frame.planRevealed}
                  approved={frame.approved}
                  pressing={frame.pressing}
                  stages={frame.stages}
                  rowsFound={frame.rowsFound}
                />
              )}
            </m.div>
          </AnimatePresence>
        </div>

        <div aria-hidden className="hidden lg:block" />

        <div className="flex min-w-0 flex-col gap-8">
          <RowStream
            columns={streamColumns}
            rows={dataset.rows}
            shown={frame.rowsShown}
            sources={plan.sources}
            windowRows={6}
            footer={<Footer sample={sample} reviewed={frame.phase === 'review' || frame.phase === 'use'} />}
          />
          {spec && (
            <div className={`transition-opacity duration-700 ease-soft ${frame.approved ? 'opacity-100' : 'opacity-40'}`}>
              <AutoChart spec={spec} />
            </div>
          )}
        </div>

        <TraceLayer sceneRef={sceneRef} rowId={traceRow} />
      </div>
    </div>
  )
}

/** Before the run ends: what the highlight colors mean. After: the cleaning report in one line. */
function Footer({ sample, reviewed }: { sample: SampleRun; reviewed: boolean }) {
  const c = sample.dataset.cleaning
  const duplicates = c.rawRows - c.uniqueRows - c.rejected.length
  const conflicts = c.conflictRowIds.length
  return (
    <div className="mt-3 flex min-h-10 items-center">
      {reviewed ? (
        <p className="animate-row-in rounded-control px-2 py-1 text-small text-ink-2">
          <span className="font-medium text-ink">
            {c.rawRows} raw rows → {c.uniqueRows} unique.
          </span>{' '}
          {duplicates} duplicates merged, {c.rejected.length} failed checks
          {conflicts > 0 && `, ${conflicts} ${conflicts === 1 ? 'value' : 'values'} where sources disagree`}.
        </p>
      ) : (
        <MethodLegend />
      )}
    </div>
  )
}
