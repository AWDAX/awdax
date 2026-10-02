import { useEffect, useRef, useState } from 'react'
import { awdax } from './awdax.ts'
import { mapLiveSnapshot, mapLiveStatus, type AwdaxpLiveState, type AwdaxpRun } from './awdaxpAdapter.ts'
import { ApiError } from './client.ts'
import { openLiveSocket } from './liveSocket.ts'
import { applyPatch, asRows, EMPTY_LIVE, isRecord, mergeSources, type LiveState } from './liveState.ts'
import { canMerge, mergeStreamedRows } from './mergeRows.ts'
import { runActivityChanged, shouldPoll } from './pollGate.ts'
import { createSnapshotGate } from './snapshotGate.ts'
import type { DatasetTable, LiveStreamPayload, ResearchSource, RunEvent, StreamedRows } from './types.ts'

export type { LiveState } from './liveState.ts'

type Handlers = {
  onPayload?: (payload: LiveStreamPayload) => void
  onChatUpdated?: () => void
}

const POLL_MS = 5000

/**
 * Live status for one instance. Prefers the WebSocket (rows as each page lands, then a reload when the
 * batch's final scoring finishes). If the socket cannot open, falls back to server-sent events plus polling.
 */
export function useLiveStream(id: string | null, handlers: Handlers = {}): LiveState {
  const [tagged, setTagged] = useState<LiveState & { forId: string | null }>({ ...EMPTY_LIVE, forId: null })
  const handlersRef = useRef(handlers)
  useEffect(() => {
    handlersRef.current = handlers
  })

  useEffect(() => {
    if (!id) return
    let closed = false
    let poll: number | undefined
    let liveRefresh: number | undefined
    let source: EventSource | null = null
    let stopSocket: (() => void) | null = null
    const datasetRef = { current: null as DatasetTable | null }
    const gate = createSnapshotGate()
    let current: LiveState = EMPTY_LIVE
    const loaded = { current: false }
    const loading = { current: false }
    const again = { current: false }
    const forceNext = { current: false }
    const includePartial = { current: false }
    const graphTick = { current: 0 }

    const filterKey = () => (includePartial.current ? 'partial' : 'accepted')
    const update = (fn: (s: LiveState) => LiveState) => {
      const before = current
      current = fn(current)
      setTagged({ ...current, forId: id })
      // A run started or finished: fetch the table now (the first load is already in flight). The end matters on
      // the event-stream fallback, which never announces the final re-merged, re-scored table.
      if (loaded.current && runActivityChanged(before.status.phase, current.status.phase)) void loadFull()
    }

    const publish = (patch: Partial<LiveState>, chatUpdated = false) => {
      const next = applyPatch(current, patch)
      update(() => next)
      handlersRef.current.onPayload?.({
        live_enabled: next.liveEnabled,
        status: next.status,
        rows_total: next.rowsTotal,
        dataset: next.dataset ?? undefined,
        chat_updated: chatUpdated,
      })
      if (chatUpdated) handlersRef.current.onChatUpdated?.()
    }

    const applyLive = (state: AwdaxpLiveState) => {
      const snap = mapLiveSnapshot(state)
      publish({ status: { ...snap.status }, liveEnabled: snap.live_enabled, rowsTotal: snap.rows_total })
    }

    const applyRows = (message: StreamedRows) => {
      const mergeable = loaded.current && canMerge(datasetRef.current)
      if (!loaded.current || gate.isLoading() || !mergeable) gate.buffer(message)
      if (!mergeable) {
        publish({ rowsTotal: message.accepted_total, partialAdded: message.partial_added, status: { lane: message.lane } })
        // Loaded but unmergeable: reload. Not loaded and nothing in flight: recover a failed first snapshot.
        if (loaded.current || !gate.isLoading()) void loadFull()
        return
      }
      datasetRef.current = mergeStreamedRows(datasetRef.current, message)
      publish({
        dataset: datasetRef.current,
        rowsTotal: message.accepted_total,
        partialAdded: message.partial_added,
        status: { lane: message.lane, current_source: message.source_url },
      })
      window.clearTimeout(liveRefresh)
      liveRefresh = window.setTimeout(() => {
        graphTick.current += 1
        update((s) => ({ ...s, graphTick: graphTick.current }))
        void loadSide()
      }, 2500)
    }

    async function loadSide() {
      try {
        const [sources, stats] = await Promise.all([awdax.getSources(id!), awdax.getStats(id!)])
        if (!closed) update((s) => ({ ...s, sources: mergeSources(s.sources, sources.sources ?? []), stats }))
      } catch {
        // Sources and scores catch up on the next batch; the table still streams.
      }
    }

    async function loadFull(forceGraph = false) {
      if (loading.current) {
        again.current = true
        forceNext.current = forceNext.current || forceGraph
        return
      }
      loading.current = true
      const force = forceGraph || forceNext.current
      forceNext.current = false
      let generation = 0
      try {
        const previous = datasetRef.current?.rows.length ?? -1
        generation = gate.begin(filterKey())
        const table = await awdax.getDataset(id!, includePartial.current)
        if (closed) return
        const merged = gate.finish(generation, filterKey(), table)
        if (!merged) return
        datasetRef.current = merged
        loaded.current = true
        if (force || merged.rows.length !== previous) graphTick.current += 1
        publish({
          dataset: merged.rows.length ? merged : null,
          rowsTotal: merged.row_count ?? merged.rows.length,
          graphTick: graphTick.current,
          includePartial: includePartial.current,
        })
        void loadSide()
      } catch (err) {
        if (closed) return
        if (err instanceof ApiError && err.status === 404) {
          update((s) => ({ ...s, missing: true }))
          gate.reset()
          again.current = false
          stopAll()
        } else update((s) => ({ ...s, connected: false }))
      } finally {
        // A failed snapshot must not leave the gate "loading", or frames would buffer forever.
        gate.settle(generation)
        loading.current = false
        if (again.current && !closed) {
          again.current = false
          void loadFull(forceNext.current)
        } else if (closed) again.current = false
      }
    }

    const onMessage = (message: unknown) => {
      if (!isRecord(message)) return
      if (message.type === 'hello' && isRecord(message.state)) {
        applyLive(message.state as unknown as AwdaxpLiveState)
        if (Array.isArray(message.events)) {
          update((s) => ({ ...s, events: (message.events as RunEvent[]).slice(-12) }))
        }
        return
      }
      if (message.type === 'status' && isRecord(message.state)) {
        applyLive(message.state as unknown as AwdaxpLiveState)
        return
      }
      if (message.type === 'run' && isRecord(message.run)) {
        const run = message.run as unknown as AwdaxpRun
        update((s) => ({
          ...s,
          connected: true,
          rowsTotal: run.rows_total ?? s.rowsTotal,
          status: { ...s.status, ...mapLiveStatus({ enabled: s.liveEnabled, latest_run: run, rows_total: run.rows_total ?? s.rowsTotal }) },
        }))
        return
      }
      if (message.type === 'run_event' && isRecord(message.event)) {
        const event = message.event as unknown as RunEvent
        update((s) => ({ ...s, events: [...s.events.filter((item) => item.id !== event.id), event].slice(-12) }))
        return
      }
      if (message.type === 'source' && isRecord(message.source)) {
        const source = message.source as unknown as ResearchSource
        if (typeof source.url !== 'string' || !source.url) return
        update((s) => ({
          ...s,
          sources: mergeSources(s.sources, [source]),
        }))
        return
      }
      const rows = asRows(message)
      if (rows) {
        applyRows(rows)
        return
      }
      if (message.type === 'batch_complete' || message.type === 'resync') {
        update((s) => ({ ...s, status: { ...s.status, lane: null } }))
        // Final scoring may have dropped rows the buffered frames still carry; the fresh snapshot is the truth.
        gate.dropBuffer()
        void loadFull(true)
        handlersRef.current.onChatUpdated?.()
      }
    }

    const startPolling = () => {
      if (poll === undefined) {
        poll = window.setInterval(() => {
          if (shouldPoll(document.visibilityState === 'visible', current.status.phase)) void loadFull()
        }, POLL_MS)
      }
    }
    // Back on the tab while polling: catch up once instead of waiting for the next tick.
    const onVisible = () => {
      if (document.visibilityState === 'visible' && poll !== undefined) void loadFull()
    }
    document.addEventListener('visibilitychange', onVisible)
    const stopPolling = () => {
      window.clearInterval(poll)
      poll = undefined
    }
    const stopSse = () => {
      source?.close()
      source = null
      stopPolling()
    }
    const startSse = () => {
      if (closed || source) return
      source = new EventSource(awdax.streamUrl(id))
      const take = (raw: string) => {
        try {
          const parsed = JSON.parse(raw) as unknown
          if (isRecord(parsed) && 'enabled' in parsed && 'latest_run' in parsed) applyLive(parsed as unknown as AwdaxpLiveState)
          else if (isRecord(parsed) && parsed.phase) {
            update((s) => ({ ...s, events: [...s.events, parsed as unknown as RunEvent].slice(-12) }))
          }
        } catch {
          // ignore
        }
      }
      source.addEventListener('status', (event) => take(event.data))
      source.addEventListener('run_event', (event) => take(event.data))
      source.addEventListener('source', (event) => {
        try {
          onMessage({ type: 'source', source: JSON.parse(event.data) as unknown })
        } catch {
          // An invalid source frame does not stop the stream.
        }
      })
      source.onmessage = (event) => take(event.data)
      source.onerror = () => {
        update((s) => ({ ...s, connected: false }))
        startPolling()
      }
      startPolling()
    }
    const stopAll = () => {
      stopSocket?.()
      stopSocket = null
      stopSse()
      window.clearTimeout(liveRefresh)
    }

    const controls = {
      refresh: () => loadFull(true),
      setIncludePartial: (value: boolean) => {
        includePartial.current = value
        update((s) => ({ ...s, includePartial: value }))
        void loadFull(true)
      },
    }
    update((s) => ({ ...s, refresh: controls.refresh, setIncludePartial: controls.setIncludePartial }))

    void loadFull()
    stopSocket = openLiveSocket(awdax.liveSocketUrl(id), {
      onMessage,
      onConnection: (state) => {
        if (state === 'open') stopSse()
        update((s) => ({ ...s, connected: state === 'open' }))
      },
      onFallback: () => startSse(),
    })

    return () => {
      closed = true
      document.removeEventListener('visibilitychange', onVisible)
      gate.reset()
      stopAll()
    }
  }, [id])

  const view = tagged.forId === id ? tagged : EMPTY_LIVE
  return view
}
