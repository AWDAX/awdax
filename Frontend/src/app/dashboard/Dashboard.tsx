import { useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { filterRows } from '../../analytics/aggregate.ts'
import type { Filter } from '../../analytics/aggregate.ts'
import type { TableProfile } from '../../analytics/profile.ts'
import type { ChartSpec } from '../../analytics/spec.ts'
import { DownloadIcon, PlusIcon, ReportIcon, TableIcon, ChartIcon, LinkIcon, MaximizeIcon, MinimizeIcon } from '../../ui/appIcons.tsx'
import { Button } from '../../ui/Button.tsx'
import { FuseButton } from '../../ui/micro/FuseButton.tsx'
import { ExportDialog } from '../export/ExportDialog.tsx'
import type { ExportScope } from '../export/scope.ts'
import { ChartPicker } from './ChartPicker.tsx'
import { DataGrid } from './DataGrid.tsx'
import { packedRows, PAGE_ROWS } from './layout.ts'
import { EMPTY_SLICERS, toFilters, valuesOf } from './slicers.ts'
import type { SlicerState } from './slicers.ts'
import { Slicers } from './Slicers.tsx'
import { KPI_TILE_PX, Tile } from './Tile.tsx'
import { RecordDetail } from '../scoring/Scoring.tsx'
import type { RecordMeta } from '../../api/types.ts'
import { useViewportHeight } from '../../ui/useViewportHeight.ts'
import { useBox } from './useBox.ts'
import type { useDashboard } from './useDashboard.ts'

type Props = {
  profile: TableProfile
  dash: ReturnType<typeof useDashboard>
  /** Used for export file names. */
  title: string
  /** The Sources tab: where the rows came from. */
  sources?: { count: number; panel: ReactNode }
  /** Charts drawn from the current table. */
  graphs?: ReactNode
  /** Score summary shown on the Data tab. */
  scoring?: ReactNode
  /** Aligned with the table rows, for the score of a picked row. */
  records?: RecordMeta[]
  /** Optionally controlled, so the page can open the Sources tab from elsewhere. */
  view?: DashboardView
  onViewChange?: (v: DashboardView) => void
}

export type DashboardView = 'report' | 'data' | 'graphs' | 'sources'
type View = DashboardView
const GAP = 16

/**
 * A Power BI-style report page for one chat: every tile on one screen (12 × 6 grid sized to the viewport),
 * slicers and click-to-filter, a Data tab with every row, and a Sources tab. Full screen hides everything else.
 */
export function Dashboard({ profile, dash, title, sources, graphs, scoring, records, view: controlled, onViewChange }: Props) {
  const [own, setOwn] = useState<View>('report')
  const view = controlled ?? own
  const setView = (v: View) => (onViewChange ? onViewChange(v) : setOwn(v))
  const [slicers, setSlicers] = useState<SlicerState>(EMPTY_SLICERS)
  const [cross, setCross] = useState<{ column: number; keys: string[]; bucket?: ChartSpec['query']['bucket'] } | null>(null)
  const [picker, setPicker] = useState<{ editing?: ChartSpec } | null>(null)
  const [exporting, setExporting] = useState<ExportScope | null>(null)
  const [drag, setDrag] = useState<{ id: string; over: number | null } | null>(null)
  const [full, setFull] = useState(false)
  const [picked, setPicked] = useState<number | null>(null)
  const section = useRef<HTMLElement>(null)
  const [canvas, box] = useBox<HTMLDivElement>()
  const wide = box.w >= 720
  const colPx = wide ? (box.w + GAP) / 12 : 0
  // One page = the screen below the toolbar. Rows are sized from the window, not the canvas, so a page with
  // more tiles than fit grows downward (pushing the questions below) instead of overlapping them.
  // Above the page: the tabs and slicers (about 104px), plus the top bar when the sidebar is closed.
  const vh = useViewportHeight()
  const pageH = Math.max(480, vh - (full ? 140 : 170))
  const even = (pageH - GAP * (PAGE_ROWS - 1)) / PAGE_ROWS
  // Number cards need KPI_TILE_PX; when an even share is less, their row takes that and the others share the rest.
  const kpiRow = dash.tiles.some((t) => t.spec.type === 'kpi') && even < KPI_TILE_PX
  const rowPx = wide ? Math.max(64, kpiRow ? (pageH - GAP * (PAGE_ROWS - 1) - KPI_TILE_PX) / (PAGE_ROWS - 1) : even) : 118
  const overflow = wide && packedRows(dash.tiles) > PAGE_ROWS

  const base = useMemo(() => toFilters(profile, slicers), [profile, slicers])
  // A tile grouped by the cross-filtered column highlights the picked groups instead of filtering itself.
  const all = useMemo<Filter[]>(() => (cross ? [...base, { column: cross.column, op: 'in', values: cross.keys, bucket: cross.bucket }] : base), [base, cross])
  const shown = useMemo(() => filterRows(profile, all).length, [profile, all])
  const filtersFor = (spec: ChartSpec) => (cross && spec.query.groupBy !== cross.column ? all : base)
  const onSelect = (spec: ChartSpec) => (key: string) => {
    const column = spec.query.groupBy
    if (column === undefined) return
    setCross((c) => {
      if (!c || c.column !== column) return { column, keys: [key], bucket: spec.query.bucket }
      const keys = c.keys.includes(key) ? c.keys.filter((k) => k !== key) : [...c.keys, key]
      return keys.length ? { ...c, keys } : null
    })
  }
  const crossLabel = cross
    ? `${profile.columns[cross.column].label}: ${cross.keys.map((k) => valuesOf(profile, cross.column).find((v) => v.key === k)?.label ?? k).join(', ')}`
    : undefined

  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === section.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])
  const toggleFull = () => (document.fullscreenElement ? void document.exitFullscreen() : void section.current?.requestFullscreen?.())

  const tablistRef = useRef<HTMLDivElement>(null)
  const [pillStyle, setPillStyle] = useState({ left: 0, width: 0, opacity: 0 })

  useEffect(() => {
    if (!tablistRef.current) return
    const activeBtn = tablistRef.current.querySelector('[aria-selected="true"]') as HTMLElement
    if (activeBtn) {
      setPillStyle({
        left: activeBtn.offsetLeft,
        width: activeBtn.offsetWidth,
        opacity: 1
      })
    }
  }, [view, sources?.count, profile.rowCount])

  const tab = (v: View, icon: ReactNode, label: ReactNode) => {
    const active = view === v
    return (
      <button
        type="button"
        role="tab"
        aria-selected={active}
        onClick={() => setView(v)}
        className={`relative z-10 flex h-9 items-center gap-1.5 rounded-control px-3 text-small transition-colors duration-200 ${active ? 'text-on-ink' : 'text-ink hover:bg-sunken'}`}
      >
        <span className={active ? 'opacity-100' : 'opacity-70'}>{icon}</span>
        <span className="flex items-center gap-1">{label}</span>
      </button>
    )
  }

  return (
    <section ref={section} aria-label="Dashboard" className={`flex flex-col transition-all duration-300 ease-out gap-3 ${full ? 'overflow-auto bg-canvas p-4' : ''}`} data-lenis-prevent>
      <div className="flex flex-wrap items-center gap-2">
        <div ref={tablistRef} role="tablist" aria-label="Dashboard view" className="relative flex gap-1 overflow-hidden rounded-panel border-2 border-ink p-0.5">
          <div
            className="absolute top-0.5 bottom-0.5 rounded-control bg-ink transition-all duration-200 ease-out"
            style={{ left: pillStyle.left, width: pillStyle.width, opacity: pillStyle.opacity }}
          />
          {tab('report', <ReportIcon />, 'Report')}
          {tab('data', <TableIcon />, <>Data <span className="font-mono text-micro opacity-70">{profile.rowCount.toLocaleString('en-IN')}</span></>)}
          {graphs && tab('graphs', <ChartIcon />, 'Graphs')}
          {sources && tab('sources', <LinkIcon />, <>Sources <span className="font-mono text-micro opacity-70">{sources.count}</span></>)}
        </div>
        <span className="ml-auto flex flex-wrap items-center gap-2">
          {view === 'report' && (
            <>
              {overflow && (
                <Button variant="secondary" onClick={dash.fit} title="Some tiles sit below the page">
                  Fit to one screen
                </Button>
              )}
              <Button onClick={() => setPicker({})}>
                <PlusIcon /> Add charts
              </Button>
            </>
          )}
          <Button variant="secondary" onClick={() => setExporting({ kind: 'rows', filters: all, label: shown === profile.rowCount ? 'All rows' : 'Filtered rows' })}>
            <DownloadIcon /> Export
          </Button>
          <Button variant="secondary" onClick={toggleFull} aria-pressed={full}>
            {full ? <><MinimizeIcon /> Exit full screen</> : <><MaximizeIcon /> Full screen</>}
          </Button>
          {view === 'report' && <FuseButton label="Reset" undoLabel="Undo" doneLabel="Reset" tone="default" onCommit={dash.reset} />}
        </span>
      </div>

      {view !== 'sources' && view !== 'graphs' && (
        <Slicers profile={profile} value={slicers} onChange={setSlicers} shown={shown} crossLabel={crossLabel} onClearCross={() => setCross(null)} />
      )}

      {/* Kept mounted (hidden on other tabs) so its measured size survives tab switches. */}
      {(
        <div ref={canvas} hidden={view !== 'report'} style={{ minHeight: wide ? pageH : undefined }}>
          <div className="grid" style={{ gap: GAP, gridTemplateColumns: wide ? 'repeat(12, minmax(0, 1fr))' : '1fr', gridAutoRows: `minmax(${rowPx}px, auto)`, gridAutoFlow: 'row dense' }}>
            {dash.tiles.map((t, i) => (
              <Tile
                key={t.spec.id}
                tile={t}
                index={i}
                count={dash.tiles.length}
                profile={profile}
                filters={filtersFor(t.spec)}
                colPx={colPx}
                rowPx={rowPx}
                gap={GAP}
                selected={cross && t.spec.query.groupBy === cross.column ? new Set(cross.keys) : undefined}
                onSelect={t.spec.query.groupBy !== undefined ? onSelect(t.spec) : undefined}
                onChange={(spec) => dash.update(t.spec.id, spec)}
                onResize={(w, h) => dash.resize(t.spec.id, w, h)}
                onMove={(to) => dash.moveTo(t.spec.id, to)}
                onRemove={() => dash.remove(t.spec.id)}
                onDuplicate={() => dash.duplicate(t.spec.id)}
                onEdit={() => setPicker({ editing: t.spec })}
                onExport={(spec) => setExporting({ kind: 'chart', spec, filters: filtersFor(spec), label: spec.title })}
                onDragStart={() => setDrag({ id: t.spec.id, over: null })}
                onDragOverTile={() => drag && drag.over !== i && setDrag({ ...drag, over: i })}
                onDragEnd={() => {
                  if (drag && drag.over !== null) dash.moveTo(drag.id, drag.over)
                  setDrag(null)
                }}
                dropTarget={drag !== null && drag.over === i && drag.id !== t.spec.id}
              />
            ))}
            {dash.tiles.length === 0 && (
              <button type="button" onClick={() => setPicker({})} className="col-span-full row-span-2 grid place-items-center rounded-panel border-2 border-dashed border-line-strong text-ink-2 hover:border-ink hover:text-ink">
                The page is empty. Add charts.
              </button>
            )}
          </div>
        </div>
      )}
      {view === 'data' && (
        <div className="flex flex-col gap-3">
          {scoring}
          <DataGrid profile={profile} filters={all} height={full ? window.innerHeight - 160 : 620} picked={picked} onPick={records ? (row) => setPicked((current) => (current === row ? null : row)) : undefined} />
          {records && <RecordDetail record={picked == null ? null : records[picked] ?? null} />}
        </div>
      )}
      {view === 'graphs' && graphs}
      {view === 'sources' && sources?.panel}

      {picker && (
        <ChartPicker
          profile={profile}
          current={dash.tiles.map((t) => t.spec)}
          editing={picker.editing}
          onAdd={dash.add}
          onUpdate={(spec) => picker.editing && dash.update(picker.editing.id, spec)}
          onClose={() => setPicker(null)}
        />
      )}
      {exporting && <ExportDialog profile={profile} scope={exporting} title={title} onClose={() => setExporting(null)} />}
    </section>
  )
}
