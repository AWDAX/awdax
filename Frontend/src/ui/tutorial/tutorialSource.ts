/** Kept apart from tutorialSeen.ts so that one stays free of import.meta and Node-testable. */
export const TUTORIAL_SRC = import.meta.env.VITE_TUTORIAL_VIDEO_URL || '/tutorial/awdax-tutorial.mp4'
export const TUTORIAL_CAPTIONS = import.meta.env.VITE_TUTORIAL_CAPTIONS_URL || '/tutorial/awdax-tutorial.vtt'
