/** Cross-tab signal so one browser tab’s instance mutations refresh the others immediately. */
const CHANNEL = 'awdax.instances.v1'

export type InstanceSyncReason = 'delete' | 'rename' | 'create' | 'mutate'

export function notifyInstancesChanged(reason: InstanceSyncReason = 'mutate') {
  try {
    new BroadcastChannel(CHANNEL).postMessage({ t: Date.now(), reason })
  } catch {
    // BroadcastChannel unavailable (some embedded WebViews)
  }
}

export function subscribeInstancesChanged(onChange: () => void): () => void {
  let channel: BroadcastChannel | null = null
  try {
    channel = new BroadcastChannel(CHANNEL)
    channel.onmessage = () => onChange()
  } catch {
    return () => {}
  }
  return () => channel?.close()
}
