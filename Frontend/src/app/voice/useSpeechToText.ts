import { useCallback, useEffect, useRef, useState } from 'react'

// Minimal Web Speech API types: not in lib.dom.d.ts, and we don't add @types packages for it.
type SpeechRecognitionErrorEvent = Event & { error: string }
type SpeechRecognitionResult = { isFinal: boolean; 0: { transcript: string } }
type SpeechRecognitionResultList = { length: number; [index: number]: SpeechRecognitionResult }
type SpeechRecognitionEvent = Event & { resultIndex: number; results: SpeechRecognitionResultList }
interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  start: () => void
  stop: () => void
  abort: () => void
  onresult: ((e: SpeechRecognitionEvent) => void) | null
  onerror: ((e: SpeechRecognitionErrorEvent) => void) | null
  onend: (() => void) | null
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
}

/** Silence before the first word: the mic turns off by itself (Chrome's own limit is about the same). */
export const NO_SPEECH_MS = 8_000
/** A pause after speaking, long enough to think mid-sentence; then the mic turns off and the text stays. */
export const PAUSE_MS = 10_000
// Chrome and Edge send audio to an online speech service, which drops an idle stream with a 'network'
// error. After this much quiet, a 'network' error is the silence, not the connection.
const IDLE_MS = 5_000

export type VoiceNotice = { tone: 'info' | 'error'; text: string }

const ERROR_TEXT: Record<string, string> = {
  'not-allowed': 'Microphone blocked. Allow it in the browser’s site settings, then try again.',
  'service-not-allowed': 'Speech recognition is turned off in this browser',
  'audio-capture': 'No microphone was found',
  'language-not-supported': 'Voice input doesn’t support this language here',
}

// Our own timer knows how long it waited; when the browser ends it for silence, we don't, so no number.
const silence = (heardAny: boolean, timed: boolean): VoiceNotice => ({
  tone: 'info',
  text: heardAny
    ? timed ? `Mic off after ${PAUSE_MS / 1000} s of silence` : 'Mic off after a long pause'
    : timed ? `Didn’t hear anything for ${NO_SPEECH_MS / 1000} s, so the mic turned off` : 'Didn’t hear anything, so the mic turned off',
})

type Options = {
  onFinal?: (text: string) => void
}

/**
 * Wraps the browser's Web Speech API. Unsupported browsers report `supported: false`. Dictation stops by
 * itself after NO_SPEECH_MS without a word, or PAUSE_MS after the last one, and says so as an info notice.
 */
export function useSpeechToText({ onFinal }: Options = {}) {
  const Ctor = typeof window !== 'undefined' ? window.SpeechRecognition ?? window.webkitSpeechRecognition : undefined
  const [listening, setListening] = useState(false)
  const [interim, setInterim] = useState('')
  const [notice, setNotice] = useState<VoiceNotice | null>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const timerRef = useRef(0)
  const lastHeardRef = useRef(0)
  const heardAnyRef = useRef(false)
  const onFinalRef = useRef(onFinal)
  useEffect(() => {
    onFinalRef.current = onFinal
  })

  const stop = useCallback(() => {
    window.clearTimeout(timerRef.current)
    recognitionRef.current?.stop()
  }, [])

  const start = useCallback(
    (lang = 'en-IN') => {
      if (!Ctor) {
        setNotice({ tone: 'error', text: 'Voice input works in Chrome and Edge' })
        return
      }
      recognitionRef.current?.abort()
      setNotice(null)
      setInterim('')
      const recognition = new Ctor()
      recognition.continuous = true
      recognition.interimResults = true
      recognition.lang = lang
      lastHeardRef.current = Date.now()
      heardAnyRef.current = false

      // Restarted on every result: the silence clock counts from the last thing heard.
      const arm = () => {
        window.clearTimeout(timerRef.current)
        timerRef.current = window.setTimeout(() => {
          if (recognitionRef.current !== recognition) return
          setNotice(silence(heardAnyRef.current, true))
          recognition.stop()
        }, heardAnyRef.current ? PAUSE_MS : NO_SPEECH_MS)
      }

      recognition.onresult = (e) => {
        if (recognitionRef.current !== recognition) return
        let finalText = ''
        let interimText = ''
        for (let i = e.resultIndex; i < e.results.length; i += 1) {
          const result = e.results[i]
          if (result.isFinal) finalText += result[0].transcript
          else interimText += result[0].transcript
        }
        lastHeardRef.current = Date.now()
        heardAnyRef.current = true
        arm()
        if (finalText) onFinalRef.current?.(finalText.trim())
        setInterim(interimText)
      }
      recognition.onerror = (e) => {
        if (recognitionRef.current !== recognition) return
        // Stopping on purpose ends with 'aborted'; that's not something to warn about.
        if (e.error === 'aborted') return
        if (e.error === 'no-speech') return setNotice(silence(heardAnyRef.current, false))
        if (e.error === 'network') {
          if (!navigator.onLine) return setNotice({ tone: 'error', text: 'You’re offline, so voice input stopped' })
          if (Date.now() - lastHeardRef.current >= IDLE_MS) return setNotice(silence(heardAnyRef.current, false))
          return setNotice({ tone: 'error', text: 'Lost the connection to the browser’s speech service. Try again.' })
        }
        setNotice({ tone: 'error', text: ERROR_TEXT[e.error] ?? 'Voice input stopped unexpectedly. Try again.' })
      }
      recognition.onend = () => {
        if (recognitionRef.current !== recognition) return
        window.clearTimeout(timerRef.current)
        recognitionRef.current = null
        setListening(false)
        setInterim('')
      }
      recognitionRef.current = recognition
      try {
        recognition.start()
      } catch {
        recognitionRef.current = null
        setNotice({ tone: 'error', text: 'Voice input couldn’t start. Try again.' })
        return
      }
      arm()
      setListening(true)
    },
    [Ctor],
  )

  // An info notice ("mic off after silence") clears itself; errors stay until the next try.
  useEffect(() => {
    if (notice?.tone !== 'info') return undefined
    const t = window.setTimeout(() => setNotice(null), 5000)
    return () => window.clearTimeout(t)
  }, [notice])

  useEffect(
    () => () => {
      window.clearTimeout(timerRef.current)
      const recognition = recognitionRef.current
      recognitionRef.current = null
      if (!recognition) return
      recognition.onresult = null
      recognition.onerror = null
      recognition.onend = null
      recognition.abort()
    },
    [],
  )

  return { supported: Boolean(Ctor), listening, interim, notice, start, stop }
}
