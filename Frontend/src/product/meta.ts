import type { Method, Permission, SourceStage } from '../domain/types.ts'

/**
 * Collection methods, cheapest first. Each method's highlighter color is its identity everywhere:
 * `dot` is the fill, `line` the darker stroke for lines, icons and text on white.
 */
export const METHOD: Record<Method, { label: string; dot: string; line: string }> = {
  structured: { label: 'Structured data', dot: 'bg-m-structured', line: 'text-m-structured-line' },
  content: { label: 'Page content', dot: 'bg-m-content', line: 'text-m-content-line' },
  rendered: { label: 'Rendered page', dot: 'bg-m-rendered', line: 'text-m-rendered-line' },
  ai: { label: 'AI reading', dot: 'bg-m-ai', line: 'text-m-ai-line' },
}

export const METHOD_ORDER: Method[] = ['structured', 'content', 'rendered', 'ai']

export const PERMISSION: Record<Permission, string> = {
  allowed: 'Allowed',
  robots_disallowed: 'Blocked by robots.txt',
  needs_login: 'Needs sign-in',
  rate_limited: 'Rate-limited',
}

export const STAGE: Record<SourceStage, string> = {
  queued: 'Queued',
  fetching: 'Fetching',
  extracting: 'Extracting',
  done: 'Done',
  skipped: 'Skipped',
  failed: 'Failed',
}
