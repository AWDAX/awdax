/** FastAPI errors are `{ "detail": "..." }`; an HTML page is a proxy/host error; else the raw text, cut short. */
export function detailOf(text: string, status: number): string {
  const trimmed = text.trim()
  if (trimmed.startsWith('<')) return `The AWDAX server didn’t answer (HTTP ${status}). Try again in a minute.`
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // not JSON
  }
  return trimmed ? trimmed.slice(0, 200) : `HTTP ${status}`
}
