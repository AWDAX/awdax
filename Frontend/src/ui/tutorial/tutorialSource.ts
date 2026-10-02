import type { VideoSource } from './tutorialSources.ts'

const override = import.meta.env.VITE_TUTORIAL_VIDEO_URL

/** Kept apart from tutorialSeen.ts so that one stays free of import.meta and Node-testable. Two encodings: a
 * browser that can't decode one (some H.264 decoders on Windows) falls through to the other. */
export const TUTORIAL_SOURCES: VideoSource[] = override
  ? [{ src: override, type: '' }]
  : [
      { src: '/tutorial/awdax-tutorial.mp4', type: 'video/mp4' },
      { src: '/tutorial/awdax-tutorial.webm', type: 'video/webm' },
    ]
export const TUTORIAL_CAPTIONS = import.meta.env.VITE_TUTORIAL_CAPTIONS_URL || '/tutorial/awdax-tutorial.vtt'
