/** Lets one async action run at a time; a call made while one is pending is ignored (returns false). */
export function createSingleFlight() {
  let pending = false
  return {
    busy: () => pending,
    async run(task: () => Promise<void>): Promise<boolean> {
      if (pending) return false
      pending = true
      try {
        await task()
        return true
      } finally {
        pending = false
      }
    },
  }
}

/** A stable key for a set of ids: reordering the list must not look like a change. */
export function sortedIdKey(items: { id: string }[]): string {
  return items.map((i) => i.id).sort().join(',')
}
