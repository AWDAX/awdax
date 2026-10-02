/**
 * Runs `fn` over `items`, at most `limit` at a time, so 50 projects don't open 50 requests at once.
 * Workers stop taking new items as soon as `isAlive()` is false (the hook was unmounted).
 */
export async function runPool<T>(
  items: T[],
  limit: number,
  fn: (x: T) => Promise<void>,
  isAlive: () => boolean = () => true,
): Promise<void> {
  let next = 0
  const worker = async () => {
    while (next < items.length && isAlive()) await fn(items[next++])
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
}

/** A live result applies only if its request started after the last manual change to that project. */
export function isFresh(startedAt: number, changedAt: number | undefined): boolean {
  return changedAt === undefined || startedAt > changedAt
}
