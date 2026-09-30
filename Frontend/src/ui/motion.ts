/**
 * Shared timing. The CSS twins are --ease-draw / --ease-soft in tokens.css and the mark / strike
 * utilities in index.css (900ms / 800ms). Slow and soft on purpose: a highlighter, not a flash.
 */
export const EASE_DRAW = [0.65, 0, 0.35, 1] as const
export const EASE_SOFT = [0.33, 1, 0.68, 1] as const

/** A trace line drawing itself, in seconds. */
export const TRACE_S = 1
/** Between one trace line and the next, in seconds. */
export const TRACE_STAGGER_S = 0.16
