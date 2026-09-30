import { useCallback, useRef, useState } from 'react'

// Low/mid/presence bands of the FFT, roughly where speech energy sits.
const BANDS: Array<[number, number]> = [
  [1, 4],
  [4, 11],
  [11, 33],
]
const GAIN = 2.2

type WebkitWindow = typeof window & { webkitAudioContext?: typeof AudioContext }

/** Opens the mic and reports a 0..1 loudness level every animation frame via `onLevel`. */
export function useMicLevel(onLevel: (level: number) => void) {
  const [error, setError] = useState<string | null>(null)
  const rafRef = useRef(0)
  const ctxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    void ctxRef.current?.close()
    ctxRef.current = null
    onLevel(0)
  }, [onLevel])

  const start = useCallback(async () => {
    setError(null)
    try {
      const Ctx = window.AudioContext ?? (window as WebkitWindow).webkitAudioContext
      if (!Ctx || !navigator.mediaDevices?.getUserMedia) throw new Error('unsupported')
      const audioCtx = new Ctx()
      const media = await navigator.mediaDevices.getUserMedia({ audio: true })
      ctxRef.current = audioCtx
      streamRef.current = media
      const source = audioCtx.createMediaStreamSource(media)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      analyser.smoothingTimeConstant = 0
      source.connect(analyser)
      const buf = new Uint8Array(analyser.frequencyBinCount)
      const tick = () => {
        analyser.getByteFrequencyData(buf)
        let total = 0
        for (const [lo, hi] of BANDS) {
          let sum = 0
          for (let i = lo; i < hi; i += 1) sum += buf[i]
          total += sum / ((hi - lo) * 255)
        }
        onLevel(Math.min(1, (total / BANDS.length) * GAIN))
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      setError('Microphone permission was denied')
    }
  }, [onLevel])

  return { error, start, stop }
}
