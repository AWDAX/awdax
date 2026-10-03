// Legacy: older builds stored web chat renames only in this browser. New renames go to PATCH /api/instances/:id.
// Uploaded-file chats are renamed in IndexedDB (renameLocal in app/files/localProjects.ts).
const KEY = 'awdax.chat.titles'
let cache: Record<string, string> | null = null

function read(): Record<string, string> {
  if (cache) return cache
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(KEY) ?? '{}')
    cache = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, string>) : {}
  } catch {
    cache = {}
  }
  return cache
}

function write(next: Record<string, string>) {
  cache = next
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage blocked: the new name lasts until the page reloads
  }
}

/** Renames a web chat in this browser. An empty title goes back to the backend's own. */
export function setChatTitle(id: string, title: string) {
  const next = { ...read() }
  const t = title.trim()
  if (t) next[id] = t
  else delete next[id]
  write(next)
}

// Duck-typed (ApiError carries `status`): client.ts reads import.meta.env, which Node tests can't import.
const isNotFound = (err: unknown) => typeof err === 'object' && err !== null && (err as { status?: unknown }).status === 404

/** One-time migration: push any browser-only titles to the backend, then drop local overrides. */
export async function migrateLocalTitlesToBackend(
  save: (id: string, title: string) => Promise<void>,
): Promise<void> {
  const local = { ...read() }
  for (const [id, title] of Object.entries(local)) {
    const t = title.trim()
    if (!t) {
      forgetChatTitle(id)
      continue
    }
    try {
      await save(id, t)
    } catch (err) {
      // 404: the chat is gone or not ours, so retrying every load is pointless. Else keep it for the next session.
      if (!isNotFound(err)) continue
    }
    forgetChatTitle(id)
  }
}

/** Drops a deleted chat's name. */
export function forgetChatTitle(id: string) {
  if (!(id in read())) return
  const next = { ...read() }
  delete next[id]
  write(next)
}
