/**
 * Start generations for the microphone. `getUserMedia` resolves later, by which time the user may have
 * stopped, restarted or left the page; a start whose generation is no longer current must release what it got.
 */
export function createStartGuard() {
  let latest = 0
  return {
    /** Begins a start and invalidates every earlier one. */
    next(): number {
      latest += 1
      return latest
    },
    /** Invalidates every outstanding start. */
    cancel(): void {
      latest += 1
    },
    isCurrent(gen: number): boolean {
      return gen === latest
    },
  }
}
