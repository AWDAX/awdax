export type VideoSource = { src: string; type: string }

/** Sources this browser says it may play, in order. An empty type (an override URL of unknown format) is kept:
 * only loading it can tell. */
export function playableSources(sources: VideoSource[], canPlayType: (type: string) => string): VideoSource[] {
  return sources.filter((s) => !s.type || canPlayType(s.type) !== '')
}
