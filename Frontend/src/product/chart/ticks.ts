/** Integer ticks from 0 up to at least max, at most five of them. Counts only, so never fractional. */
export function ticks(max: number): number[] {
  const step = Math.max(1, Math.ceil(max / 4))
  const out: number[] = []
  for (let v = 0; v <= max; v += step) out.push(v)
  if (out[out.length - 1] < max) out.push(out[out.length - 1] + step)
  return out
}
