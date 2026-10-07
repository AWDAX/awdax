/**
 * "Near me": a request that asks for places around the person needs where they are. The browser's position is
 * requested only for such a request, never ahead of time, and only the rounded coordinates leave the page.
 * Refusing (or no answer in a few seconds) is fine: the backend then uses its configured default centre, or asks for a
 * city.
 */
const NEAR_ME = /\b(near\s*me|nearby|near\s+by|around\s+me|close\s+to\s+me|my\s+(?:location|area|neighbou?rhood))\b/i

export const wantsMyLocation = (text: string): boolean => NEAR_ME.test(text)

export type Position = { lat: number; lng: number }

const round = (n: number) => Math.round(n * 1000) / 1000 // about 100 m: enough to search around, not to find a door

export function currentPosition(timeoutMs = 5000): Promise<Position | null> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) return Promise.resolve(null)
  return new Promise((resolve) => {
    // Some browsers never call back when the prompt is ignored, so the wait is bounded here too.
    const timer = setTimeout(() => resolve(null), timeoutMs + 500)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(timer)
        resolve({ lat: round(pos.coords.latitude), lng: round(pos.coords.longitude) })
      },
      () => {
        clearTimeout(timer)
        resolve(null)
      },
      { timeout: timeoutMs, maximumAge: 10 * 60_000, enableHighAccuracy: false },
    )
  })
}
