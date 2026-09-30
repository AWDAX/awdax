import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useReducedMotion } from 'motion/react'
import { MicIcon, StopIcon } from '../appIcons.tsx'
import { useMicLevel } from './useMicLevel.ts'
import { drawWaveform, pushLevel } from './drawWaveform.ts'
import type { WaveHistory } from './drawWaveform.ts'

export type VoicePillStopReason = 'toggle' | 'escape' | 'disabled' | 'mic-denied' | 'unmount' | 'ended'

export type VoicePillProps = {
  onStart?: () => void
  onStop?: (reason: VoicePillStopReason) => void
  disabled?: boolean
  /** What's really listening (e.g. the speech recognizer). When it ends on its own, the pill resets too. */
  listening?: boolean
  ariaLabel?: string
  /** Diameter in px. */
  size?: number
  className?: string
}

function formatElapsed(ms: number) {
  const s = Math.floor(ms / 1000)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** Mic button for the chat composer: tap to start, tap (or Escape) to stop. The waveform reacts
 * to live mic input via getUserMedia + an AnalyserNode. Shape is always the rounded square. */
export function VoicePill({ onStart, onStop, disabled = false, listening: active, ariaLabel = 'Dictate', size = 36, className = '' }: VoicePillProps) {
  const [listening, setListening] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const reduceMotion = useReducedMotion()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const historyRef = useRef<WaveHistory>({ bars: [] })
  const startedAtRef = useRef(0)

  const onLevel = (level: number) => {
    if (reduceMotion || !canvasRef.current) return
    pushLevel(historyRef.current, level)
    drawWaveform(canvasRef.current, historyRef.current.bars, 'var(--color-ink)')
  }
  const mic = useMicLevel(onLevel)

  const stop = (reason: VoicePillStopReason) => {
    if (!listening) return
    mic.stop()
    historyRef.current.bars = []
    setListening(false)
    onStop?.(reason)
  }
  const begin = () => {
    if (disabled || listening) return
    historyRef.current.bars = []
    startedAtRef.current = Date.now()
    setElapsed(0)
    setListening(true)
    onStart?.()
    void mic.start()
  }

  useEffect(() => {
    if (!mic.error) return undefined
    // Deferred: stop() sets state, and effects must not call a state setter synchronously.
    const id = window.setTimeout(() => stop('mic-denied'), 0)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mic.error])
  useEffect(() => {
    if (!listening) return undefined
    const id = window.setInterval(() => setElapsed(Date.now() - startedAtRef.current), 250)
    return () => window.clearInterval(id)
  }, [listening])
  useEffect(() => {
    if (!disabled) return undefined
    const id = window.setTimeout(() => stop('disabled'), 0)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled])
  useEffect(() => {
    if (active !== false || !listening) return undefined
    const id = window.setTimeout(() => stop('ended'), 0)
    return () => window.clearTimeout(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, listening])
  useEffect(() => () => stop('unmount'), []) // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = () => (listening ? stop('toggle') : begin())
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (e.key === 'Escape' && listening) stop('escape')
  }

  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-label={ariaLabel}
        aria-pressed={listening}
        onClick={toggle}
        onKeyDown={onKeyDown}
        style={{ width: size, height: size }}
        className={
          'inline-flex shrink-0 items-center justify-center rounded-control border-2 transition-[background-color,border-color,color,scale] duration-300 ease-soft active:scale-97 ' +
          'disabled:pointer-events-none disabled:opacity-45 focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-ink ' +
          (listening ? 'border-ink bg-ink text-signal' : 'border-ink bg-surface text-ink hover:bg-sunken')
        }
      >
        {listening ? <StopIcon /> : <MicIcon />}
      </button>
      {listening && (
        <span className="inline-flex items-center gap-2">
          <canvas ref={canvasRef} width={56} height={20} className="h-5 w-14 text-ink" aria-hidden />
          <span className="font-mono text-micro text-ink-3 tabular-nums">{formatElapsed(elapsed)}</span>
        </span>
      )}
    </span>
  )
}
