type Reader = Pick<Storage, 'getItem'> | null
type Writer = Pick<Storage, 'setItem'> | null

export function seenKey(userId: string | null): string {
  return `awdax.tutorial.seen.v1:${userId ?? 'anon'}`
}

/** Blocked or missing storage counts as seen: a user we can't remember is never nagged. */
export function hasSeenTutorial(storage: Reader, userId: string | null): boolean {
  if (!storage) return true
  try {
    return storage.getItem(seenKey(userId)) !== null
  } catch {
    return true
  }
}

export function markTutorialSeen(storage: Writer, userId: string | null): void {
  if (!storage) return
  try {
    storage.setItem(seenKey(userId), '1')
  } catch {
    // storage blocked: nothing to remember with
  }
}
