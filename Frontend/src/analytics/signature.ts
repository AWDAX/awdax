import type { TableProfile } from './profile.ts'

/**
 * The table's real column names, in order. Saved state that points at columns by index (dashboard tiles,
 * answers) is only reused while this is unchanged; virtual columns follow from the real ones, so they're left out.
 */
export const columnSignature = (p: TableProfile) =>
  p.columns
    .filter((c) => !c.virtual)
    .map((c) => c.name)
    .join('|')
