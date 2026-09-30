import { useEffect, useState } from 'react'
import { VoicePill } from '../../ui/micro/VoicePill.tsx'
import { useSpeechToText } from './useSpeechToText.ts'
import type { VoiceNotice } from './useSpeechToText.ts'

type Props = {
  onTranscript: (finalText: string) => void
  onInterim?: (text: string) => void
  disabled?: boolean
  className?: string
}

const DENIED: VoiceNotice = { tone: 'error', text: 'Microphone blocked. Allow it in the browser’s site settings, then try again.' }

/**
 * VoicePill wired to the Web Speech API: dictates into the prompt box. Unsupported browsers (anything but
 * Chrome and Edge) get a disabled pill with an explanatory title. When dictation ends by itself (silence, or
 * the browser's speech service), the pill resets and a note under it says why, without moving the box.
 */
export function VoiceInput({ onTranscript, onInterim, disabled = false, className = '' }: Props) {
  const speech = useSpeechToText({ onFinal: onTranscript })
  const [pillError, setPillError] = useState<VoiceNotice | null>(null)
  const notice = speech.notice ?? pillError

  useEffect(() => {
    if (speech.interim !== '') onInterim?.(speech.interim)
  }, [speech.interim, onInterim])

  return (
    <span className={`relative inline-flex ${className}`} title={speech.supported ? undefined : 'Voice input works in Chrome and Edge'}>
      <VoicePill
        ariaLabel={speech.listening ? 'Stop dictating' : 'Dictate'}
        disabled={disabled || !speech.supported}
        listening={speech.listening}
        onStart={() => {
          setPillError(null)
          speech.start()
        }}
        onStop={(reason) => {
          speech.stop()
          if (reason === 'mic-denied') setPillError(DENIED)
        }}
      />
      {notice && (
        <span
          role={notice.tone === 'error' ? 'alert' : 'status'}
          className={`absolute top-full right-0 z-20 mt-1 w-max max-w-64 rounded-control border-2 bg-surface px-2 py-1 text-micro ${
            notice.tone === 'error' ? 'border-blocked text-blocked' : 'border-ink text-ink-2'
          }`}
        >
          {notice.text}
        </span>
      )}
    </span>
  )
}
