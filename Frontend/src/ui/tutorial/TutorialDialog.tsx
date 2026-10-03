import { useEffect, useId, useRef, useState } from 'react'
import { CloseIcon } from '../appIcons.tsx'
import { Button } from '../Button.tsx'
import { useFocusTrap } from '../useFocusTrap.ts'
import { TUTORIAL_CAPTIONS, TUTORIAL_SOURCES } from './tutorialSource.ts'

// Header, footer and padding take about 15rem; the video gets the rest of the screen height, at 16:9.
const VIDEO_WIDTH = 'min(100%, calc((100dvh - 15rem) * 16 / 9))'

/** The tutorial video in a modal that always fits the screen. It starts on its own; browsers refuse sound
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

  const last = TUTORIAL_SOURCES.length - 1
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-3 backdrop-blur-[2px] sm:p-6"
      data-lenis-prevent
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={trap}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className="flex max-h-full w-full max-w-5xl flex-col overflow-y-auto rounded-panel border-2 border-ink bg-surface p-4 shadow-[4px_4px_0px_var(--color-ink)] sm:p-5"
      >
        <div className="mb-4 flex items-start gap-4">
          <div className="min-w-0">
            <p className="font-mono text-micro text-ink-3">Tutorial · 1 min 20 s</p>
            <h2 id={headingId} className="mt-0.5 font-display font-wide text-h3 font-extrabold">
              How AWDAX works
            </h2>
            <p className="mt-1 text-small text-ink-2">
              Start a request, approve the plan, watch the live run, and read your project reports.
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="ml-auto grid size-9 shrink-0 place-items-center rounded-control border-2 border-transparent hover:border-ink hover:bg-sunken focus-visible:outline-2 focus-visible:outline-ink"
          >
            <CloseIcon />
          </button>
        </div>

        {failed ? (
          <div className="grid place-items-center gap-2 rounded-panel border-2 border-dashed border-line-strong bg-sunken px-6 py-12 text-center">
            <p className="font-display font-wide text-body font-extrabold">This browser couldn’t play the tutorial.</p>
            <p className="max-w-md text-small text-ink-2">
              Try opening it on its own, or come back to it any time from the compass button.
            </p>
            <a
              href={TUTORIAL_SOURCES[0].src}
              target="_blank"
              rel="noreferrer"
              className="mt-2 text-small font-semibold underline underline-offset-4 hover:text-ink-2"
            >
              Open the video in a new tab
            </a>
          </div>
        ) : (
          <div
            className="mx-auto aspect-video overflow-hidden rounded-panel border-2 border-ink bg-ink"
            style={{ width: VIDEO_WIDTH }}
          >
            <video
              ref={video}
              controls
              playsInline
              preload="metadata"
              className="size-full"
              onEnded={() => setEnded(true)}
              onVolumeChange={(e) => setMuted(e.currentTarget.muted)}
            >
              {TUTORIAL_SOURCES.map((s, i) => (
                // The browser moves to the next source on its own; only the last one failing means nothing plays.
                <source key={s.src} src={s.src} type={s.type || undefined} onError={i === last ? () => setFailed(true) : undefined} />
              ))}
              <track kind="captions" src={TUTORIAL_CAPTIONS} srcLang="en" label="English" default />
            </video>
          </div>
        )}

        <div className="mt-4 flex flex-wrap items-center justify-end gap-2">
          <p className="mr-auto hidden font-mono text-micro text-ink-3 sm:block">Esc closes · replay it any time from the compass</p>
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
