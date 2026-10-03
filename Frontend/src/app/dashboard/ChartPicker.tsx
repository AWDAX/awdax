import { useEffect, useMemo, useState } from 'react'
import type { TableProfile } from '../../analytics/profile.ts'
import { CHART_LABEL } from '../../analytics/spec.ts'
import type { ChartSpec, ChartType } from '../../analytics/spec.ts'
import { suggestCharts } from '../../analytics/suggest.ts'
import { ArrowIcon, CheckIcon } from '../../ui/icons.tsx'
import { CloseIcon, PlusIcon } from '../../ui/appIcons.tsx'
import { useFocusTrap } from '../../ui/useFocusTrap.ts'
import { ChartBuilder } from './ChartBuilder.tsx'
import { GALLERY, unavailable } from './chartTypes.ts'
import { ChartTypeIcon } from './ChartTypeIcon.tsx'

type Props = {
  profile: TableProfile
  /** Specs already on the dashboard, so suggestions can say "added". */
  current: ChartSpec[]
  /** Set when editing an existing tile: opens straight into the builder. */
  editing?: ChartSpec
  onAdd: (spec: ChartSpec) => void
  onUpdate: (spec: ChartSpec) => void
  onClose: () => void
}

const same = (a: ChartSpec, b: ChartSpec) => a.type === b.type && JSON.stringify(a.query) === JSON.stringify(b.query) && a.x === b.x && a.y === b.y

/**
 * "Add charts", like Power BI's Visualizations pane: first a gallery of chart pictures (column, bar, line, area,
 * pie, donut, scatter, number card, table). Picking one opens the builder set up for it, with a live preview.
 * Ready-made suggestions for this table sit under the gallery, each saying why it fits.
 */
export function ChartPicker({ profile, current, editing, onAdd, onUpdate, onClose }: Props) {
  const [building, setBuilding] = useState<ChartType | null>(editing ? editing.type : null)
  const trap = useFocusTrap<HTMLDivElement>(true)
  const ideas = useMemo(() => suggestCharts(profile), [profile])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 sm:p-10" data-lenis-prevent onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={trap} role="dialog" aria-modal="true" aria-label={editing ? 'Edit chart' : 'Add charts'} className="w-full max-w-4xl rounded-panel border-2 border-ink bg-surface p-5">
        <div className="mb-4 flex items-center gap-3 border-b-2 border-ink pb-3">
          {building && !editing && (
            <button type="button" onClick={() => setBuilding(null)} className="inline-flex h-8 items-center gap-1.5 rounded-control px-2 text-small text-ink-2 hover:bg-sunken hover:text-ink">
              <ArrowIcon className="rotate-180" /> All charts
            </button>
          )}
          <h2 className="font-display text-h3 font-extrabold">{editing ? 'Edit chart' : building ? 'Build the chart' : 'Add charts'}</h2>
          <button type="button" aria-label="Close" onClick={onClose} className="ml-auto grid size-8 place-items-center rounded-control hover:bg-sunken">
            <CloseIcon />
          </button>
        </div>

        {building ? (
          <ChartBuilder
            // Keyed by the picked type, so going back and picking another starts the builder fresh.
            key={building}
            profile={profile}
            initial={editing}
            startType={building}
            onCancel={editing ? onClose : () => setBuilding(null)}
            onSave={(spec) => {
              if (editing) onUpdate(spec)
              else onAdd(spec)
              onClose()
            }}
          />
        ) : (
          <div className="flex flex-col gap-6">
            <section aria-labelledby="gallery-heading">
              <h3 id="gallery-heading" className="text-small font-semibold">
                Pick a visual
              </h3>
              <ul className="mt-2 grid gap-2 sm:grid-cols-3">
                {GALLERY.map(({ type, best }) => {
                  const why = unavailable(profile, type)
                  return (
                    <li key={type}>
                      <button
                        type="button"
                        disabled={why !== null}
                        onClick={() => setBuilding(type)}
                        className="group flex h-full w-full items-center gap-3 rounded-panel border-2 border-line p-3 text-left transition-colors duration-300 ease-soft hover:border-ink hover:bg-signal-soft disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:border-line disabled:hover:bg-transparent"
                      >
                        <span className="grid h-12 w-16 shrink-0 place-items-center rounded-control bg-sunken transition-colors duration-300 ease-soft group-hover:bg-surface">
                          <ChartTypeIcon type={type} className="h-8 w-11" />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-small font-semibold">{CHART_LABEL[type]}</span>
                          <span className="block text-micro text-ink-3">{why ?? best}</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>

            <section aria-labelledby="suggested-heading">
              <h3 id="suggested-heading" className="text-small font-semibold">
                Suggested for this data
              </h3>
              <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                {ideas.map((s) => {
                  const added = current.some((c) => same(c, s))
                  return (
                    <li key={s.id}>
                      <button
                        type="button"
                        disabled={added}
                        onClick={() => onAdd(s)}
                        className="flex h-full w-full items-start gap-3 rounded-panel border-2 border-line p-3 text-left transition-colors duration-300 ease-soft hover:border-ink disabled:cursor-default disabled:bg-sunken disabled:hover:border-line"
                      >
                        <span className={`grid size-7 shrink-0 place-items-center rounded-control border-2 ${added ? 'border-ink bg-signal' : 'border-ink'}`}>{added ? <CheckIcon /> : <PlusIcon />}</span>
                        <span className="min-w-0">
                          <span className="block text-small font-semibold">{s.title}</span>
                          <span className="block font-mono text-micro text-ink-3">{CHART_LABEL[s.type]}{added ? ' · on the dashboard' : ''}</span>
                          <span className="mt-1 block text-small text-ink-2">{s.reason}</span>
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
