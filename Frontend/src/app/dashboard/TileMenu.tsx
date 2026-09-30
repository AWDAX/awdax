import { useCallback, useRef, useState } from 'react'
import type { QueryResult } from '../../analytics/aggregate.ts'
import { CHART_LABEL } from '../../analytics/spec.ts'
import type { ChartSpec, ChartType } from '../../analytics/spec.ts'
import { MoreIcon } from '../../ui/appIcons.tsx'
import { CheckIcon } from '../../ui/icons.tsx'
import { Popover } from '../../ui/Popover.tsx'
import { useFocusTrap } from '../../ui/useFocusTrap.ts'
import { CHART_COLORS } from './chartColor.ts'

type Props = {
  spec: ChartSpec
  index: number
  count: number
  w: number
  h: number
  canResize: boolean
  result: QueryResult
  /** Chart types to offer here when the tile is too narrow for its own type switch. */
  types: ChartType[]
  onChange: (spec: ChartSpec) => void
  onResize: (w: number, h: number) => void
  onMove: (to: number) => void
  onRemove: () => void
  onDuplicate: () => void
  onEdit: () => void
  onExport: (spec: ChartSpec) => void
}

const item =
  'flex w-full items-center justify-between gap-4 rounded-control px-2.5 py-1.5 text-left text-small hover:bg-sunken focus-visible:bg-sunken focus-visible:outline-none disabled:opacity-40 disabled:hover:bg-transparent'

/** A tile's commands. Every drag action (move, resize) also lives here, so keyboards can do it too. */
export function TileMenu({ spec, index, count, w, h, canResize, types, onChange, onResize, onMove, onRemove, onDuplicate, onEdit, onExport }: Props) {
  const [open, setOpen] = useState(false)
  const anchor = useRef<HTMLButtonElement>(null)
  // Focus moves into the open menu; arrow keys, Home and End move between items; closing returns focus.
  const menu = useFocusTrap<HTMLDivElement>(open, { arrows: true })
  const close = useCallback(() => setOpen(false), [])

  const run = (fn: () => void) => () => {
    fn()
    setOpen(false)
  }

  return (
    <div className="relative shrink-0">
      <button
        ref={anchor}
        type="button"
        aria-label={`More for ${spec.title}`}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((o) => !o)}
        className="grid size-6 place-items-center rounded-control text-ink-2 hover:bg-sunken hover:text-ink focus-visible:outline-2 focus-visible:outline-ink"
      >
        <MoreIcon />
      </button>
      {/* Rendered outside the tile (a portal), so a small tile can never clip its own menu. */}
      <Popover anchor={anchor} open={open} onClose={close} boxRef={menu} role="menu" label={`Actions for ${spec.title}`} className="flex w-56 flex-col p-1">
          {types.length > 1 && (
            <div className="flex flex-wrap gap-1 border-b border-line p-1.5 pb-2" role="group" aria-label="Show as">
              {types.map((t) => (
                <button
                  key={t}
                  role="menuitemradio"
                  aria-checked={spec.type === t}
                  type="button"
                  onClick={run(() => onChange({ ...spec, type: t }))}
                  className={`rounded-control border-2 px-2 py-0.5 text-micro ${spec.type === t ? 'border-ink bg-signal' : 'border-line hover:border-ink'}`}
                >
                  {CHART_LABEL[t]}
                </button>
              ))}
            </div>
          )}
          {spec.type !== 'table' && (
            <div className="border-b border-line p-1.5 pb-2" role="group" aria-label="Colour">
              <p className="mb-1.5 px-1 font-mono text-micro text-ink-3">Colour</p>
              <div className="flex flex-wrap gap-1">
                {CHART_COLORS.map((c) => {
                  const on = (spec.color ?? 'ink') === c.key
                  return (
                    <button
                      key={c.key}
                      role="menuitemradio"
                      aria-checked={on}
                      aria-label={c.label}
                      title={c.label}
                      type="button"
                      onClick={() => onChange({ ...spec, color: c.key === 'ink' ? undefined : c.key })}
                      className={`grid size-6 place-items-center rounded-control text-on-ink outline-offset-2 transition-[outline-color,scale] duration-200 ease-soft hover:scale-110 focus-visible:outline-2 focus-visible:outline-ink ${c.swatch} ${
                        on ? 'outline-2 outline-ink' : 'outline-2 outline-transparent'
                      }`}
                    >
                      {on && <CheckIcon className="size-3.5" />}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
          <button role="menuitem" type="button" className={item} onClick={run(onEdit)}>
            Edit chart…
          </button>
          {spec.type !== 'kpi' && spec.type !== 'table' && spec.type !== 'scatter' && (
            <button role="menuitemcheckbox" aria-checked={!!spec.labels} type="button" className={item} onClick={run(() => onChange({ ...spec, labels: !spec.labels }))}>
              Value labels <span className="font-mono text-micro text-ink-3">{spec.labels ? 'on' : 'off'}</span>
            </button>
          )}
          <button role="menuitem" type="button" className={item} onClick={run(() => onExport(spec))}>
            Export this data…
          </button>
          <button role="menuitem" type="button" className={item} onClick={run(onDuplicate)}>
            Duplicate
          </button>
          <hr className="my-1 border-line" />
          <button role="menuitem" type="button" className={item} disabled={index === 0} onClick={run(() => onMove(index - 1))}>
            Move earlier
          </button>
          <button role="menuitem" type="button" className={item} disabled={index === count - 1} onClick={run(() => onMove(index + 1))}>
            Move later
          </button>
          {canResize && (
            <>
              <button role="menuitem" type="button" className={item} disabled={w >= 12} onClick={() => onResize(w + 1, h)}>
                Wider <span className="font-mono text-micro text-ink-3">{w}/12</span>
              </button>
              <button role="menuitem" type="button" className={item} disabled={w <= 2} onClick={() => onResize(w - 1, h)}>
                Narrower
              </button>
              <button role="menuitem" type="button" className={item} disabled={h >= 6} onClick={() => onResize(w, h + 1)}>
                Taller <span className="font-mono text-micro text-ink-3">{h}/6 rows</span>
              </button>
              <button role="menuitem" type="button" className={item} disabled={h <= 1} onClick={() => onResize(w, h - 1)}>
                Shorter
              </button>
            </>
          )}
          <hr className="my-1 border-line" />
          <button role="menuitem" type="button" className={`${item} text-blocked`} onClick={run(onRemove)}>
            Remove from dashboard
          </button>
      </Popover>
    </div>
  )
}
