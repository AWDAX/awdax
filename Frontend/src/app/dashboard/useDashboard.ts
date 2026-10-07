import { useCallback, useEffect, useMemo, useState } from 'react'
import type { TableProfile } from '../../analytics/profile.ts'
import { columnSignature } from '../../analytics/signature.ts'
import { newId } from '../../analytics/spec.ts'
import type { ChartSpec } from '../../analytics/spec.ts'
import { suggestCharts } from '../../analytics/suggest.ts'
import { scopedKey } from '../auth/userScope.ts'
import { clampH, clampW, layoutPage, sizeFor } from './layout.ts'
import type { Tile } from './layout.ts'

export type { Tile } from './layout.ts'

interface Saved {
  /** The table's column names when this layout was made; a re-scrape with other columns starts over. */
  signature: string
  tiles: Tile[]
}

// v2: tiles are sized in page rows (1–6) on a one-screen canvas. Older layouts (88px rows) are not reused.
const keyFor = (instanceId: string) => scopedKey(`awdax.dashboard.v2.${instanceId}`)
const fresh = (specs: ChartSpec[]) => specs.map((spec) => ({ ...spec, id: newId() }))

/** The default page: the number cards and the first four charts the table supports. */
function initial(p: TableProfile): Tile[] {
  const ideas = suggestCharts(p).filter((s) => s.type !== 'table')
  const kpis = ideas.filter((s) => s.type === 'kpi')
  const charts = ideas.filter((s) => s.type !== 'kpi').slice(0, 4)
  return layoutPage(fresh([...kpis, ...charts]))
}

function load(instanceId: string, p: TableProfile): Tile[] {
  try {
    const raw = localStorage.getItem(keyFor(instanceId))
    if (raw) {
      const saved = JSON.parse(raw) as Saved
      if (saved.signature === columnSignature(p) && Array.isArray(saved.tiles)) {
        return saved.tiles.map((t) => ({ ...t, w: clampW(t.w), h: clampH(t.h) }))
      }
    }
  } catch {
    // unreadable or blocked storage: start fresh
  }
  return initial(p)
}

/**
 * The tiles for one chat's dashboard, saved in this browser per chat (a layout is a personal view, not data).
 * When the scraped table's columns change, the saved layout no longer fits and the suggestions return.
 */
export function useDashboard(instanceId: string, profile: TableProfile) {
  const signature = columnSignature(profile)
  const [state, setState] = useState(() => ({ signature, tiles: load(instanceId, profile) }))
  // A new column set (another scrape) replaces the tiles during render, not in an effect.
  const tiles = state.signature === signature ? state.tiles : load(instanceId, profile)
  if (state.signature !== signature) setState({ signature, tiles })

  useEffect(() => {
    try {
      localStorage.setItem(keyFor(instanceId), JSON.stringify({ signature, tiles } satisfies Saved))
    } catch {
      // storage full or blocked: the layout just isn't remembered
    }
  }, [instanceId, signature, tiles])

  const set = useCallback((fn: (t: Tile[]) => Tile[]) => setState((s) => ({ ...s, tiles: fn(s.tiles) })), [])

  const actions = useMemo(
    () => ({
      add: (spec: ChartSpec) => {
        const [w, h] = sizeFor(spec.type)
        set((t) => [...t, { spec: { ...spec, id: newId() }, w, h }])
      },
      update: (id: string, spec: ChartSpec) => set((t) => t.map((x) => (x.spec.id === id ? { ...x, spec: { ...spec, id } } : x))),
      remove: (id: string) => set((t) => t.filter((x) => x.spec.id !== id)),
      duplicate: (id: string) =>
        set((t) => {
          const i = t.findIndex((x) => x.spec.id === id)
          if (i < 0) return t
          const copy = { ...t[i], spec: { ...t[i].spec, id: newId() } }
          return [...t.slice(0, i + 1), copy, ...t.slice(i + 1)]
        }),
      resize: (id: string, w: number, h: number) => set((t) => t.map((x) => (x.spec.id === id ? { ...x, w: clampW(w), h: clampH(h) } : x))),
      /** Moves a tile to another position in the order (the grid flows left to right, top to bottom). */
      moveTo: (id: string, to: number) =>
        set((t) => {
          const from = t.findIndex((x) => x.spec.id === id)
          if (from < 0) return t
          const next = [...t]
          const [item] = next.splice(from, 1)
          next.splice(Math.max(0, Math.min(next.length, to)), 0, item)
          return next
        }),
      /** Re-sizes every tile, in its current order, so the page fits one screen again. */
      fit: () => set((t) => layoutPage(t.map((x) => x.spec))),
      reset: () => set(() => initial(profile)),
    }),
    [set, profile],
  )

  return { tiles, ...actions }
}
