import type { Method } from '../domain/types.ts'

export type MarkInk = 'yellow' | Method

/**
 * Highlighter color classes (index.css). Yellow is AWDAX; the others are collection methods.
 * Kept out of Mark.tsx so that file exports only a component (React Fast Refresh).
 */
export const MARK: Record<MarkInk, string> = {
  yellow: 'mark-yellow',
  structured: 'mark-structured',
  content: 'mark-content',
  rendered: 'mark-rendered',
  ai: 'mark-ai',
}
