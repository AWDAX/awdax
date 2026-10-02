import { useEffect, useId, useRef, useState } from 'react'
import { CloseIcon } from '../appIcons.tsx'
import { Button } from '../Button.tsx'
import { useFocusTrap } from '../useFocusTrap.ts'
import { TUTORIAL_CAPTIONS, TUTORIAL_SRC } from './tutorialSource.ts'

/** The tutorial video in a modal, modelled on ExportDialog. It starts on its own; browsers refuse sound
 * before the first click, so it then starts muted and offers Unmute. Skip closes it at any point. */
export function TutorialDialog({ onClose }: { onClose: () => void }) {
  const trap = useFocusTrap<HTMLDivElement>(true)
  const headingId = useId()
  const video = useRef<HTMLVideoElement>(null)
  const [failed, setFailed] = useState(false)
  const [muted, setMuted] = useState(false)
  const [ended, setEnded] = useState(false)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    const el = video.current
    if (!el) return
    el.play().catch(() => {
      if (video.current !== el) return
      el.muted = true
      setMuted(true)
      el.play().catch(() => {
        // Autoplay is off entirely: the viewer presses play on the controls.
      })
    })
  }, [])

  const toggleMute = () => {
    const el = video.current
    if (!el) return
    el.muted = !el.muted
    setMuted(el.muted)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink/40 p-4 sm:p-10" data-lenis-prevent onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={trap} role="dialog" aria-modal="true" aria-labelledby={headingId} className="w-full max-w-5xl rounded-panel border-2 border-ink bg-surface p-5">
        <div className="mb-4 flex items-start gap-4 border-b-2 border-ink pb-3">
          <div>
            <h2 id={headingId} className="font-display font-wide text-h3 font-extrabold">How AWDAX works</h2>
            <p className="text-small text-ink-2">A short walkthrough: start a request, approve the plan, watch the live run, and read your project reports.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="ml-auto grid size-8 shrink-0 place-items-center rounded-control hover:bg-sunken">
            <CloseIcon />
          </button>
        </div>

        <div className="aspect-video w-full overflow-hidden rounded-panel bg-ink">
          {failed ? (
            <div className="grid size-full place-items-center p-6 text-center text-on-ink">The tutorial video isn't available yet.</div>
          ) : (
            <video
              ref={video}
              src={TUTORIAL_SRC}
              controls
              playsInline
              preload="metadata"
              className="size-full"
              onError={() => setFailed(true)}
              onEnded={() => setEnded(true)}
              onVolumeChange={(e) => setMuted(e.currentTarget.muted)}
            >
              <track kind="captions" src={TUTORIAL_CAPTIONS} srcLang="en" label="English" default />
            </video>
          )}
        </div>

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          {!failed && (
            <Button variant="secondary" onClick={toggleMute} aria-pressed={muted}>
              {muted ? 'Unmute' : 'Mute'}
            </Button>
          )}
          <Button variant={ended || failed ? 'primary' : 'secondary'} onClick={onClose}>
            {ended || failed ? 'Done' : 'Skip tutorial'}
          </Button>
        </div>
      </div>
    </div>
  )
}
