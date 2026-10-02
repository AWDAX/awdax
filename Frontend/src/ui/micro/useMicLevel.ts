import { useCallback, useEffect, useRef, useState } from 'react'
import { createStartGuard } from './micSession.ts'

// Low/mid/presence bands of the FFT, roughly where speech energy sits.
const BANDS: Array<[number, number]> = [
  [1, 4],
  [4, 11],
  [11, 33],
]
const GAIN = 2.2

type WebkitWindow = typeof window & { webkitAudioContext?: typeof AudioContext }

/** Opens the mic and reports a 0..1 loudness level every animation frame via `onLevel`.
 * The hook owns the stream: `stop()` and unmount release it, and a start that is overtaken
 * while waiting for permission releases what it was given instead of keeping the mic on. */
export function useMicLevel(onLevel: (level: number) => void) {
  const [error, setError] = useState<string | null>(null)
  const rafRef = useRef(0)
  const ctxRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const guardRef = useRef(createStartGuard())
  const onLevelRef = useRef(onLevel)
  useEffect(() => {
    onLevelRef.current = onLevel
  })

  const release = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    void ctxRef.current?.close()
    ctxRef.current = null
  }, [])

  const stop = useCallback(() => {
    guardRef.current.cancel()
    release()
    onLevelRef.current(0)
  }, [release])

  const start = useCallback(async () => {
    const guard = guardRef.current
    const gen = guard.next()
    release()
    setError(null)
    let audioCtx: AudioContext | null = null
    let media: MediaStream | null = null
    try {
      const Ctx = window.AudioContext ?? (window as WebkitWindow).webkitAudioContext
      if (!Ctx || !navigator.mediaDevices?.getUserMedia) throw new Error('unsupported')
      audioCtx = new Ctx()
      media = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!guard.isCurrent(gen)) {
        // Stopped, restarted or unmounted while the permission prompt was open.
        media.getTracks().forEach((t) => t.stop())
        void audioCtx.close()
        return
      }
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
        onLevelRef.current(Math.min(1, (total / BANDS.length) * GAIN))
        rafRef.current = requestAnimationFrame(tick)
      }
      tick()
    } catch {
      // A failure after the grant must not leave the microphone live.
      media?.getTracks().forEach((t) => t.stop())
      if (media && streamRef.current === media) streamRef.current = null
      void audioCtx?.close()
      if (ctxRef.current === audioCtx) ctxRef.current = null
      if (guard.isCurrent(gen)) setError('Microphone permission was denied')
    }
  }, [release])

  // Leaving the page always turns the mic off, whatever the caller thinks its own state is.
  useEffect(() => stop, [stop])

  return { error, start, stop }
}
