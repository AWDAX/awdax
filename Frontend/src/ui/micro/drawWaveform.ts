/** A scrolling bar history the mic level is pushed into, drawn to a canvas. Kept as plain
 * functions (not a component) so VoicePill.tsx exports only the component (react-refresh). */
export type WaveHistory = { bars: number[] }

export function pushLevel(history: WaveHistory, level: number, max = 26) {
  history.bars.push(level)
  if (history.bars.length > max) history.bars.shift()
}

export function drawWaveform(canvas: HTMLCanvasElement, bars: number[], color: string) {
  const dpr = Math.min(2, window.devicePixelRatio || 1)
  const rect = canvas.getBoundingClientRect()
  const w = Math.max(1, Math.round(rect.width * dpr))
  const h = Math.max(1, Math.round(rect.height * dpr))
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w
    canvas.height = h
  }
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.clearRect(0, 0, w, h)
  ctx.fillStyle = color
  const barW = 2 * dpr
  const step = barW + 2 * dpr
  for (let i = 0; i < bars.length; i += 1) {
    const level = bars[bars.length - 1 - i]
    const x = w - (i + 1) * step
    if (x + barW < 0) break
    const barH = Math.max(barW, level * h)
    ctx.fillRect(x, (h - barH) / 2, barW, barH)
  }
}
