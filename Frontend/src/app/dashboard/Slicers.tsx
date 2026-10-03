import { useCallback, useMemo, useRef, useState } from 'react'
import type { ColumnProfile, TableProfile } from '../../analytics/profile.ts'
import { ChevronIcon, FilterIcon, SearchIcon } from '../../ui/appIcons.tsx'
import { Popover } from '../../ui/Popover.tsx'
import { Select } from '../../ui/Select.tsx'
import { activeCount, EMPTY_SLICERS, periodKeys, slicerColumns, valuesOf } from './slicers.ts'
import type { SlicerState } from './slicers.ts'

type Props = {
  profile: TableProfile
  value: SlicerState
  onChange: (next: SlicerState) => void
  /** Rows that pass every filter, out of all rows. */
  shown: number
  /** A cross-filter from clicking a chart, shown here so it can be cleared. */
  crossLabel?: string
  onClearCross?: () => void
}

const field = 'h-9 rounded-control border-2 border-line bg-surface px-2.5 text-small hover:border-ink focus-visible:border-ink focus-visible:outline-none'

/** Power BI-style slicers: search, category pickers and a period range. They filter every tile at once. */
export function Slicers({ profile, value, onChange, shown, crossLabel, onClearCross }: Props) {
  const { cats, time } = useMemo(() => slicerColumns(profile), [profile])
  const periods = useMemo(() => (time ? periodKeys(profile, time.index) : []), [profile, time])
  const active = activeCount(value) + (crossLabel ? 1 : 0)

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className={`${field} flex w-full items-center gap-2 sm:w-64`}>
        <SearchIcon className="shrink-0 text-ink-3" />
        <span className="sr-only">Search rows</span>
        <input
          type="search"
          value={value.search}
          onChange={(e) => onChange({ ...value, search: e.target.value })}
          placeholder="Search every column"
          className="w-full min-w-0 bg-transparent outline-none placeholder:text-ink-3"
        />
      </label>

      {cats.map((c) => (
        <Picker key={c.index} profile={profile} column={c} picked={value.picks[c.index] ?? []} onPick={(keys) => onChange({ ...value, picks: { ...value.picks, [c.index]: keys } })} />
      ))}

      {time && periods.length > 1 && (
        <span className="flex items-center gap-1.5 text-small">
          <span className="text-ink-3">{time.label}</span>
          <Select
            label={`${time.label} from`}
            value={value.from ?? ''}
            onChange={(from) => onChange({ ...value, from: from || undefined })}
            options={[{ value: '', label: 'From start' }, ...periods.map((p) => ({ value: p.key, label: p.label }))]}
          />
          <span className="text-ink-3">to</span>
          <Select
            label={`${time.label} to`}
            value={value.to ?? ''}
            onChange={(to) => onChange({ ...value, to: to || undefined })}
            options={[{ value: '', label: 'End' }, ...periods.map((p) => ({ value: p.key, label: p.label }))]}
          />
        </span>
      )}

      {crossLabel && (
        <button type="button" onClick={onClearCross} className="flex h-9 items-center gap-1.5 rounded-control border-2 border-ink bg-signal px-2.5 text-small font-medium" title="Clear this chart filter">
          {crossLabel} <span aria-hidden>×</span>
        </button>
      )}

      <span className="ml-auto flex items-center gap-3 font-mono text-micro text-ink-3">
        {shown.toLocaleString('en-IN')} of {profile.rowCount.toLocaleString('en-IN')} rows
        {active > 0 && (
          <button
            type="button"
            onClick={() => {
              onChange(EMPTY_SLICERS)
              onClearCross?.()
            }}
            className="font-sans text-small text-ink underline underline-offset-2 hover:text-ink-2"
          >
            Clear filters ({active})
          </button>
        )}
      </span>
    </div>
  )
}

function Picker({ profile, column, picked, onPick }: { profile: TableProfile; column: ColumnProfile; picked: string[]; onPick: (keys: string[]) => void }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const box = useRef<HTMLButtonElement>(null)
  const values = useMemo(() => valuesOf(profile, column.index), [profile, column.index])
  const shown = q ? values.filter((v) => v.label.toLowerCase().includes(q.toLowerCase())) : values

  const close = useCallback(() => setOpen(false), [])

  const toggle = (key: string) => onPick(picked.includes(key) ? picked.filter((k) => k !== key) : [...picked, key])
  const summary = picked.length === 0 ? 'All' : picked.length === 1 ? values.find((v) => v.key === picked[0])?.label : `${picked.length} picked`

  return (
    <div className="relative">
      <button ref={box} type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className={`${field} flex items-center gap-1.5 ${picked.length ? 'border-ink bg-signal-soft' : ''}`}>
        <FilterIcon className="text-ink-3" />
        <span className="text-ink-3">{column.label}:</span>
        <span className="max-w-32 truncate font-medium">{summary}</span>
        <ChevronIcon className="rotate-90 text-ink-3" />
      </button>
      <Popover anchor={box} open={open} onClose={close} align="start" label={`Filter by ${column.label}`} className="flex w-64 flex-col gap-1 p-2">
          {values.length > 8 && (
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Find a ${column.label.toLowerCase()}`} className="mb-1 h-8 rounded-control border-2 border-line px-2 text-small outline-none focus:border-ink" />
          )}
          <ul className="max-h-64 overflow-auto" data-lenis-prevent>
            {shown.map((v) => (
              <li key={v.key}>
                <label className="flex cursor-pointer items-center gap-2 rounded-control px-1.5 py-1 text-small hover:bg-sunken">
                  <input type="checkbox" checked={picked.includes(v.key)} onChange={() => toggle(v.key)} className="size-4 accent-ink" />
                  <span className="min-w-0 flex-1 truncate">{v.label}</span>
                  <span className="font-mono text-micro text-ink-3">{v.count}</span>
                </label>
              </li>
            ))}
          </ul>
          {picked.length > 0 && (
            <button type="button" onClick={() => onPick([])} className="mt-1 self-start text-small underline underline-offset-2">
              Select all
            </button>
          )}
      </Popover>
    </div>
  )
}
