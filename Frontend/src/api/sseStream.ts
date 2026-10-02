import type { AwdaxpLiveState } from './awdaxpAdapter.ts'
import { isRecord } from './liveState.ts'
import type { RunEvent } from './types.ts'

type Handlers = {
  onLive: (state: AwdaxpLiveState) => void
  onEvent: (event: RunEvent) => void
  onSource: (source: unknown) => void
}

/** Wires the stream's frames to the hook. Frames that fail to parse are skipped; they never stop the stream. */
export function attachStreamListeners(source: EventSource, handlers: Handlers) {
  const take = (raw: string) => {
    try {
      const parsed = JSON.parse(raw) as unknown
      if (isRecord(parsed) && 'enabled' in parsed && 'latest_run' in parsed) handlers.onLive(parsed as unknown as AwdaxpLiveState)
      else if (isRecord(parsed) && parsed.phase) handlers.onEvent(parsed as unknown as RunEvent)
    } catch {
      // ignore
    }
  }
  source.addEventListener('status', (event) => take(event.data))
  source.addEventListener('run_event', (event) => take(event.data))
  source.addEventListener('source', (event) => {
    try {
      handlers.onSource(JSON.parse(event.data) as unknown)
    } catch {
      // An invalid source frame does not stop the stream.
    }
  })
  source.onmessage = (event) => take(event.data)
}
