export type ListToken = { req: number; mut: number }

/**
 * Orders list reads against each other and against local changes. A read is accepted only if no newer read
 * has already been applied and nothing was created, renamed or deleted since it began. A slow read that a newer
 * request overtook still lands when nothing newer has landed yet, so a slow backend can't keep the list stale.
 */
export function createListSequence() {
  let req = 0
  let mut = 0
  let applied = 0
  return {
    begin(): ListToken {
      req += 1
      return { req, mut }
    },
    accept(t: ListToken): boolean {
      if (t.mut !== mut || t.req <= applied) return false
      applied = t.req
      return true
    },
    mutated(): void {
      mut += 1
    },
  }
}
