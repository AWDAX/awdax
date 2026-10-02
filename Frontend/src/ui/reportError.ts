/** The one place a crash is reported. Wire an external reporter here later; callers never change. */
export function reportError(error: unknown, info?: { componentStack?: string }): void {
  console.error('[awdax]', error, info?.componentStack)
}
